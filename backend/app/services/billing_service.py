import json

from app.db import connect
from app.engines.helpers import kwh_qty
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill
from app.modules.outage_credit import (
    CreditExceeded,
    CreditError,
    GrossReadingMissing,
    apply_credit,
    validate_registration,
)
from app.repositories import accounts as accounts_repo
from app.repositories import credits as credits_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo


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

    def settings_map(self):
        return settings_repo.get_map(self._conn)

    # ---- 停电电量信用 ----

    def _gross_kwh(self, account_id: int) -> float:
        gross = readings_repo.latest_kwh(self._conn, account_id)
        if gross is None:
            raise GrossReadingMissing("该户暂无抄表记录，无法取得账期毛电量")
        return gross

    def list_credits(self, account_id: int, period: str | None = None):
        return credits_repo.list_for_account(self._conn, account_id, period)

    def register_credit(self, account_id: int, period: str, kwh: float, reason: str | None):
        if not accounts_repo.get(self._conn, account_id):
            raise CreditError("户号不存在")
        gross = self._gross_kwh(account_id)
        active_total = credits_repo.active_total(self._conn, account_id, period)
        # 超额在此抛出 CreditExceeded，router 转为带差额明细的 4xx
        validate_registration(kwh, gross, active_total)
        entry = credits_repo.insert(self._conn, account_id, period, kwh, reason)
        new_total = credits_repo.active_total(self._conn, account_id, period)
        return {
            "credit": entry,
            "gross_kwh": kwh_qty(gross),
            "active_total": kwh_qty(new_total),
            "remaining_capacity": kwh_qty(max(0.0, gross - new_total)),
        }

    def void_credit(self, credit_id: int, reason: str | None):
        entry = credits_repo.get(self._conn, credit_id)
        if entry is None:
            raise CreditError("信用记录不存在")
        if not entry["active"]:
            raise CreditError("该信用记录已作废，不能重复作废")
        return credits_repo.void(self._conn, credit_id, reason)

    def run_bill(
        self,
        kwh: float,
        peak: bool,
        account_id: int | None,
        persist: bool,
        period: str | None = None,
    ):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0

        gross = kwh_qty(kwh)
        credit_total = 0.0
        entries: list[dict] = []
        if account_id is not None and period:
            credit_total = kwh_qty(credits_repo.active_total(self._conn, account_id, period))
            entries = [
                c for c in credits_repo.list_for_account(self._conn, account_id, period)
                if c["active"]
            ]
        deducted, net = apply_credit(gross, credit_total)
        deducted, net = kwh_qty(deducted), kwh_qty(net)

        result = calc_bill(net, tiers, factor)
        result.update(
            {
                "gross_kwh": gross,
                "net_kwh": net,
                "credit": {
                    "period": period,
                    "total": credit_total,
                    "deducted": deducted,
                    "entries": entries,
                },
            }
        )
        run_id = None
        if persist:
            run_id = runs_repo.insert(
                self._conn,
                "bill",
                {
                    "kwh": kwh,
                    "peak": peak,
                    "account_id": account_id,
                    "period": period,
                    "credit_total": credit_total,
                },
                result,
                account_id,
            )
        return {"run_id": run_id, **result}

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
