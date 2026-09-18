from app.db import connect
from app.engines.helpers import kwh_qty
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill
from app.repositories import accounts as accounts_repo
from app.repositories import credits as credits_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo

EPS = 1e-6


class CreditError(Exception):
    """Business-rule violation when registering/voiding outage credits."""

    def __init__(self, message: str, code: str = "credit_rejected", extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.extra = extra or {}


class BillingService:
    def __init__(self):
        self._conn = connect()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def list_accounts(self):
        return accounts_repo.list_all(self._conn)

    def get_account(self, account_id: int):
        return accounts_repo.get(self._conn, account_id)

    def list_tiers(self):
        return tiers_repo.list_ordered(self._conn)

    def list_readings(self):
        return readings_repo.list_all(self._conn)

    def readings_for_account(self, account_id: int):
        return readings_repo.for_account(self._conn, account_id)

    def periods_for_account(self, account_id: int):
        return readings_repo.periods_for_account(self._conn, account_id)

    def settings_map(self):
        return settings_repo.get_map(self._conn)

    # ------------------------------------------------------------------ credits

    def list_credits(self, account_id: int, period: str | None = None):
        return credits_repo.list_for_account(self._conn, account_id, period)

    def period_summary(self, account_id: int, period: str) -> dict:
        account = accounts_repo.get(self._conn, account_id)
        if not account:
            raise CreditError(f"户号不存在: {account_id}", "account_not_found")
        totals = readings_repo.period_totals(self._conn, account_id, period)
        if totals is None:
            raise CreditError(f"账期 {period} 尚无抄表毛电量，无法核对停电信用", "no_gross_reading")
        gross = totals["gross_kwh"]
        peak = totals["peak"]
        credit_rows = credits_repo.list_for_account(self._conn, account_id, period)
        active = [r for r in credit_rows if r["status"] == "active"]
        credit_total = round(sum(float(r["kwh"]) for r in active), 3)
        net = kwh_qty(max(0.0, gross - credit_total))
        return {
            "account_id": account_id,
            "period": period,
            "gross_kwh": kwh_qty(gross),
            "peak": peak,
            "credit_kwh": credit_total,
            "net_kwh": net,
            "credits": credit_rows,
        }

    def register_credit(self, account_id: int, period: str, kwh: float, note: str | None) -> dict:
        if kwh is None or kwh <= EPS:
            raise CreditError("信用电量必须大于 0", "invalid_kwh")
        account = accounts_repo.get(self._conn, account_id)
        if not account:
            raise CreditError(f"户号不存在: {account_id}", "account_not_found")
        totals = readings_repo.period_totals(self._conn, account_id, period)
        if totals is None:
            raise CreditError(
                f"账期 {period} 尚无抄表毛电量，请先录入抄表后再登记停电信用",
                "no_gross_reading",
            )
        gross = totals["gross_kwh"]
        kwh = round(float(kwh), 3)
        # 单笔不得超过该账期毛电量
        if kwh > gross + EPS:
            excess = kwh_qty(kwh - gross)
            raise CreditError(
                f"单笔信用电量 {kwh} kWh 超过该账期毛电量 {kwh_qty(gross)} kWh，超限 {excess} kWh，登记已拒绝",
                "credit_exceeds_gross",
                {"gross_kwh": kwh_qty(gross), "excess_kwh": excess},
            )
        # 多笔有效信用累加后也不得超过该账期毛电量
        current = credits_repo.active_sum(self._conn, account_id, period)
        new_sum = round(current + kwh, 3)
        if new_sum > gross + EPS:
            excess = kwh_qty(new_sum - gross)
            raise CreditError(
                f"本笔 {kwh} kWh 登记后有效信用合计为 {new_sum} kWh，"
                f"超过该账期毛电量 {kwh_qty(gross)} kWh，超限 {excess} kWh，登记已拒绝",
                "credit_total_exceeds_gross",
                {
                    "gross_kwh": kwh_qty(gross),
                    "active_credit_kwh": kwh_qty(current),
                    "excess_kwh": excess,
                },
            )
        credit_id = credits_repo.insert(self._conn, account_id, period, kwh, note)
        row = credits_repo.get(self._conn, credit_id)
        return {
            "credit": row,
            "active_credit_kwh": kwh_qty(new_sum),
            "gross_kwh": kwh_qty(gross),
            "remaining_kwh": kwh_qty(max(0.0, gross - new_sum)),
        }

    def void_credit(self, credit_id: int, note: str | None) -> dict:
        row = credits_repo.get(self._conn, credit_id)
        if not row:
            raise CreditError(f"信用记录不存在: #{credit_id}", "credit_not_found")
        if row["status"] == "void":
            raise CreditError(
                f"信用记录 #{credit_id} 已于 {row.get('voided_at')} 作废，不能重复作废（审计行仍保留）",
                "credit_already_void",
            )
        credits_repo.void(self._conn, credit_id, note)
        return credits_repo.get(self._conn, credit_id)

    # ------------------------------------------------------------------- billing

    def run_bill(
        self,
        kwh: float | None,
        peak: bool,
        account_id: int | None,
        persist: bool,
        period: str | None = None,
    ) -> dict:
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0

        credits = []
        credit_total = 0.0
        if account_id is not None and period:
            summary = self.period_summary(account_id, period)
            gross = float(summary["gross_kwh"])
            credit_total = float(summary["credit_kwh"])
            credits = [r for r in summary["credits"] if r["status"] == "active"]
            net = kwh_qty(max(0.0, gross - credit_total))
            source = {"mode": "period", "account_id": account_id, "period": period}
        elif kwh is not None:
            gross = float(kwh)
            net = kwh_qty(gross)
            source = {"mode": "manual", "account_id": account_id}
        else:
            raise CreditError("请提供户号与账期，或直接输入电量", "missing_input")

        # 计费基数为净电量（毛电量扣除有效停电信用合计），再走分段与尖峰
        result = calc_bill(net, tiers, factor)
        run_id = None
        if persist:
            run_id = runs_repo.insert(
                self._conn,
                "bill",
                {
                    **source,
                    "gross_kwh": kwh_qty(gross),
                    "peak": peak,
                    "credit_kwh": kwh_qty(credit_total),
                    "net_kwh": net,
                    "credit_ids": [c["id"] for c in credits],
                },
                result,
                account_id,
            )
        return {
            "run_id": run_id,
            "account_id": account_id,
            "period": period,
            "gross_kwh": kwh_qty(gross),
            "credit_kwh": kwh_qty(credit_total),
            "net_kwh": net,
            "credits": [
                {"id": c["id"], "kwh": c["kwh"], "note": c.get("note"), "created_at": c.get("created_at")}
                for c in credits
            ],
            **result,
        }

    def run_compare(self, kwh: float, persist: bool):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        result = compare_plain_vs_peak(kwh, tiers, pf)
        run_id = None
        if persist:
            run_id = runs_repo.insert(self._conn, "compare", {"kwh": kwh}, result, None)
        return {"run_id": run_id, **result}

    def list_history(self, limit: int = 50):
        return runs_repo.list_recent(self._conn, limit)

    def get_run(self, run_id: int):
        return runs_repo.get(self._conn, run_id)

    def dashboard_stats(self):
        accounts = accounts_repo.list_all(self._conn)
        readings = readings_repo.list_all(self._conn)
        clean = [a for a in accounts if "种子" not in a.get("name", "")]
        dirty = [a for a in accounts if "种子" in a.get("name", "")]
        return {
            "account_count": len(accounts),
            "reading_count": len(readings),
            "clean_accounts": len(clean),
            "dirty_accounts": len(dirty),
            "recent_runs": len(runs_repo.list_recent(self._conn, 5)),
        }
