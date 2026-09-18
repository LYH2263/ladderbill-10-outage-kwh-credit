import pytest

from app import seed
from app.modules.outage_credit import (
    CreditExceeded,
    GrossReadingMissing,
    apply_credit,
    validate_registration,
)
from app.services.billing_service import BillingService

GROSS = 120.0
PERIOD = "2026-09"


# ---------- 纯领域规则（无需数据库） ----------


def test_entry_larger_than_gross_rejected():
    with pytest.raises(CreditExceeded) as ei:
        validate_registration(kwh=130, gross_kwh=120, active_total=0)
    assert ei.value.scope == "entry"
    assert ei.value.over_limit == 10
    assert ei.value.gross_kwh == 120


def test_cumulative_total_over_gross_rejected():
    validate_registration(kwh=100, gross_kwh=120, active_total=0)
    with pytest.raises(CreditExceeded) as ei:
        validate_registration(kwh=30, gross_kwh=120, active_total=100)
    assert ei.value.scope == "total"
    # 合计 130 - 毛电量 120 = 超限 10
    assert ei.value.over_limit == 10
    assert ei.value.active_total == 100


def test_cumulative_up_to_gross_allowed():
    total = validate_registration(kwh=100, gross_kwh=120, active_total=0)
    total = validate_registration(kwh=20, gross_kwh=120, active_total=total)
    assert total == 120


def test_non_positive_credit_rejected():
    from app.modules.outage_credit import CreditError

    with pytest.raises(CreditError):
        validate_registration(kwh=0, gross_kwh=120, active_total=0)


def test_apply_credit_deducts_and_nets():
    deducted, net = apply_credit(gross_kwh=120, active_total=50)
    assert deducted == 50
    assert net == 70
    # 信用合计不应把净电量扣成负数
    deducted, net = apply_credit(gross_kwh=120, active_total=999)
    assert deducted == 120
    assert net == 0


# ---------- 服务层 + 临时数据库 ----------


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    import app.db as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    seed.init_db()
    with BillingService() as s:
        yield s


def test_register_accumulates_and_reports_capacity(svc):
    out1 = svc.register_credit(1, PERIOD, 50, "停电半天")
    assert out1["active_total"] == 50
    assert out1["remaining_capacity"] == 70
    out2 = svc.register_credit(1, PERIOD, 40, None)
    assert out2["active_total"] == 90
    assert out2["remaining_capacity"] == 30
    assert len(svc.list_credits(1, PERIOD)) == 2


def test_register_over_capacity_is_refused_with_delta(svc):
    svc.register_credit(1, PERIOD, 100, None)
    with pytest.raises(CreditExceeded) as ei:
        svc.register_credit(1, PERIOD, 30, None)
    assert ei.value.scope == "total"
    assert ei.value.over_limit == 10
    # 被拒绝的登记不得落库
    assert len(svc.list_credits(1, PERIOD)) == 1


def test_register_without_reading_raises(svc):
    # 种子库中只有户 1、2，新建一个无抄表的户
    cur = svc._conn.execute("INSERT INTO accounts(name, meter_no, note) VALUES ('新户','M-9999','')")
    new_id = cur.lastrowid
    svc._conn.commit()
    with pytest.raises(GrossReadingMissing):
        svc.register_credit(new_id, PERIOD, 10, None)


def test_bill_deducts_credit_towards_net(svc):
    svc.register_credit(1, PERIOD, 50, None)
    r = svc.run_bill(GROSS, False, 1, persist=False, period=PERIOD)
    assert r["gross_kwh"] == 120
    assert r["credit"]["total"] == 50
    assert r["credit"]["deducted"] == 50
    assert r["net_kwh"] == 70
    # 分段基于净电量 70 而非毛电量 120
    assert sum(seg["qty"] for seg in r["segments"]) == 70
    assert r["total"] == 36.40


def test_void_removes_deduction_but_keeps_audit_row(svc):
    entry = svc.register_credit(1, PERIOD, 50, None)["credit"]
    before = svc.run_bill(GROSS, False, 1, persist=False, period=PERIOD)
    assert before["net_kwh"] == 70

    voided = svc.void_credit(entry["id"], "误登记")
    assert voided["active"] is False
    assert voided["status"] == "void"
    assert voided["void_reason"] == "误登记"

    # 作废后再次测算：净电量回升到毛电量
    after = svc.run_bill(GROSS, False, 1, persist=False, period=PERIOD)
    assert after["credit"]["total"] == 0
    assert after["credit"]["deducted"] == 0
    assert after["net_kwh"] == 120

    # 审计行仍可查阅
    rows = svc.list_credits(1, PERIOD)
    assert len(rows) == 1
    assert rows[0]["status"] == "void"


def test_void_twice_rejected(svc):
    from app.modules.outage_credit import CreditError

    entry = svc.register_credit(1, PERIOD, 10, None)["credit"]
    svc.void_credit(entry["id"], None)
    with pytest.raises(CreditError):
        svc.void_credit(entry["id"], None)


def test_credits_scoped_by_period(svc):
    svc.register_credit(1, "2026-08", 100, None)
    # 不同账期独立累计、独立校验
    out = svc.register_credit(1, PERIOD, 120, None)
    assert out["active_total"] == 120
    r = svc.run_bill(GROSS, False, 1, persist=False, period=PERIOD)
    assert r["net_kwh"] == 0
