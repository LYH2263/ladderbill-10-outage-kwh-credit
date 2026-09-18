"""停电电量信用（outage credit）领域规则。

- 信用按户（account）+ 账期（period，如 "2026-09"）登记，可多笔累加。
- 单笔电量与有效（未作废）信用合计均不得超过该账期毛电量，否则拒绝登记。
- 计费时以 毛电量 - 有效信用合计 得净电量，再做阶梯分段与尖峰系数。
- 作废只置标记位（见 repositories.credits），审计行保留，不再参与扣除。
"""

from app.engines.helpers import kwh_qty

# 浮点容差：120.0000001 这类存储误差不应被误判为超额
EPS = 1e-9


class CreditError(Exception):
    """信用模块业务错误基类。"""


class GrossReadingMissing(CreditError):
    """该户没有抄表记录，无法取得账期毛电量作为信用上限。"""


class CreditExceeded(CreditError):
    """信用电量超出账期毛电量上限。

    scope="entry"：单笔本身已超过毛电量；scope="total"：单笔合规但累加后超额。
    """

    def __init__(
        self,
        message: str,
        *,
        scope: str,
        gross_kwh: float,
        requested: float,
        active_total: float,
        over_limit: float,
    ):
        super().__init__(message)
        self.scope = scope
        self.gross_kwh = kwh_qty(gross_kwh)
        self.requested = kwh_qty(requested)
        self.active_total = kwh_qty(active_total)
        self.over_limit = kwh_qty(over_limit)

    def to_detail(self) -> dict:
        return {
            "code": "credit_exceeded",
            "scope": self.scope,
            "message": str(self),
            "gross_kwh": self.gross_kwh,
            "requested": self.requested,
            "active_total": self.active_total,
            "over_limit": self.over_limit,
        }


def validate_registration(kwh: float, gross_kwh: float, active_total: float) -> float:
    """校验一笔新信用登记，返回登记后的有效合计；超额抛 CreditExceeded。"""
    kwh = float(kwh)
    gross = float(gross_kwh)
    active = float(active_total)
    if kwh <= 0:
        raise CreditError("信用电量必须大于 0")
    if gross < 0:
        raise CreditError("账期毛电量不能为负")
    if kwh > gross + EPS:
        raise CreditExceeded(
            f"单笔信用 {kwh_qty(kwh)} kWh 超过本账期毛电量 {kwh_qty(gross)} kWh，"
            f"超限 {kwh_qty(kwh - gross)} kWh",
            scope="entry",
            gross_kwh=gross,
            requested=kwh,
            active_total=active,
            over_limit=kwh - gross,
        )
    projected = active + kwh
    if projected > gross + EPS:
        over = projected - gross
        raise CreditExceeded(
            f"登记后信用合计 {kwh_qty(projected)} kWh 超过本账期毛电量 "
            f"{kwh_qty(gross)} kWh，超限 {kwh_qty(over)} kWh"
            f"（已有有效信用 {kwh_qty(active)} kWh，本笔最多还可登记 "
            f"{kwh_qty(gross - active)} kWh）",
            scope="total",
            gross_kwh=gross,
            requested=kwh,
            active_total=active,
            over_limit=over,
        )
    return projected


def apply_credit(gross_kwh: float, active_total: float) -> tuple[float, float]:
    """毛电量扣除有效信用合计，返回 (实际扣除量, 净电量)。"""
    gross = max(0.0, float(gross_kwh))
    credited = min(gross, max(0.0, float(active_total)))
    return credited, gross - credited
