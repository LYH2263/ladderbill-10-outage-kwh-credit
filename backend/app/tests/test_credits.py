from app.tests.conftest import PERIOD


def _register(client, account_id, kwh, period=PERIOD, note=None):
    return client.post(
        f"/api/accounts/{account_id}/credits",
        json={"period": period, "kwh": kwh, "note": note},
    )


def test_seed_credits_accumulate_and_net_is_gross_minus_credits(client):
    # 李家：毛 400，有效信用 20 + 10 = 30，净 370
    r = client.get(f"/api/accounts/2/credits?period={PERIOD}")
    assert r.status_code == 200
    body = r.json()
    assert body["gross_kwh"] == 400.0
    assert body["credit_kwh"] == 30.0
    assert body["net_kwh"] == 370.0
    assert len(body["items"]) == 2


def test_seed_void_credit_is_audit_only(client):
    # 张家唯一一笔信用已作废：不参与扣除，净电量 = 毛电量
    r = client.get(f"/api/accounts/1/credits?period={PERIOD}")
    body = r.json()
    assert body["credit_kwh"] == 0.0
    assert body["net_kwh"] == 120.0
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == "void"
    assert body["items"][0]["void_note"]


def test_bill_uses_net_kwh_with_peak_segments(client):
    r = client.post(
        "/api/bill",
        json={"account_id": 2, "period": PERIOD, "peak": True, "persist": False},
    )
    assert r.status_code == 200
    b = r.json()
    assert b["gross_kwh"] == 400.0
    assert b["credit_kwh"] == 30.0
    assert b["net_kwh"] == 370.0
    assert b["kwh"] == 370.0  # 计费基数是净电量
    # 180*0.52*1.2 + 80*0.62*1.2 + 110*0.82*1.2 = 280.08
    assert b["total"] == 280.08
    assert len(b["segments"]) == 3
    assert sum(s["qty"] for s in b["segments"]) == 370.0
    assert {c["id"] for c in b["credits"]} == {2, 3}


def test_preview_bill_does_not_write_run(client):
    before = len(client.get("/api/history").json()["items"])
    r = client.post(
        "/api/bill",
        json={"account_id": 2, "period": PERIOD, "persist": False},
    )
    assert r.status_code == 200
    assert r.json()["run_id"] is None
    after = len(client.get("/api/history").json()["items"])
    assert before == after


def test_persisted_bill_records_credit_deduction(client):
    r = client.post(
        "/api/bill",
        json={"account_id": 2, "period": PERIOD, "persist": True},
    )
    run_id = r.json()["run_id"]
    assert run_id
    run = client.get(f"/api/history/{run_id}").json()
    import json

    payload = json.loads(run["input_json"])
    assert payload["gross_kwh"] == 400.0
    assert payload["credit_kwh"] == 30.0
    assert payload["net_kwh"] == 370.0
    assert payload["credit_ids"] == [2, 3]


def test_multiple_credits_accumulate(client):
    assert _register(client, 1, 30).status_code == 201
    r = _register(client, 1, 40)
    assert r.status_code == 201
    assert r.json()["active_credit_kwh"] == 70.0
    assert r.json()["gross_kwh"] == 120.0
    assert r.json()["remaining_kwh"] == 50.0


def test_single_credit_over_gross_is_rejected_with_excess(client):
    r = _register(client, 1, 130)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "credit_exceeds_gross"
    assert detail["gross_kwh"] == 120.0
    assert detail["excess_kwh"] == 10.0
    assert "130" in detail["message"] and "超限 10" in detail["message"]


def test_accumulated_credits_over_gross_is_rejected_with_excess(client):
    _register(client, 1, 50)
    _register(client, 1, 50)
    r = _register(client, 1, 20.5)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "credit_total_exceeds_gross"
    assert detail["active_credit_kwh"] == 100.0
    assert detail["excess_kwh"] == 0.5
    assert "120.5" in detail["message"]
    # 被拒的一笔没有入库：张家本有 1 笔作废审计行 + 2 笔新有效行
    items = client.get(f"/api/accounts/1/credits?period={PERIOD}").json()["items"]
    assert len(items) == 3
    assert sum(1 for i in items if i["status"] == "active") == 2


def test_register_without_gross_reading_rejected(client):
    r = _register(client, 1, 10, period="2026-09")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "no_gross_reading"


def test_register_unknown_account_404(client):
    assert _register(client, 999, 10).status_code == 404


def test_non_positive_credit_is_422(client):
    assert _register(client, 1, 0).status_code == 422


def test_void_removes_credit_from_deduction_but_keeps_row(client):
    # 作废李家第一笔 20 kWh (种子 id=2)
    r = client.post("/api/credits/2/void", json={"note": "复核无误，撤销"})
    assert r.status_code == 200
    credit = r.json()["credit"]
    assert credit["status"] == "void"
    assert credit["void_note"] == "复核无误，撤销"
    assert credit["voided_at"]

    summary = client.get(f"/api/accounts/2/credits?period={PERIOD}").json()
    assert summary["credit_kwh"] == 10.0          # 只剩第二笔
    assert summary["net_kwh"] == 390.0            # 净电量回升 20
    assert len(summary["items"]) == 2             # 作废行仍可查阅

    bill = client.post(
        "/api/bill",
        json={"account_id": 2, "period": PERIOD, "persist": False},
    ).json()
    assert bill["credit_kwh"] == 10.0
    assert bill["net_kwh"] == 390.0
    assert [c["id"] for c in bill["credits"]] == [3]


def test_void_is_idempotent_rejected(client):
    # 种子里张家 #1 已是作废状态
    r = client.post("/api/credits/1/void", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "credit_already_void"


def test_void_unknown_credit_404(client):
    r = client.post("/api/credits/999/void", json={})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "credit_not_found"


def test_credit_cannot_reaccumulate_past_gross_after_void_boundary(client):
    # 120 毛电量：登 100 → 再登 20（恰好到顶，允许）→ 再登 0.01 必须拒绝
    assert _register(client, 1, 100).status_code == 201
    assert _register(client, 1, 20).status_code == 201
    r = _register(client, 1, 0.01)
    assert r.status_code == 409
    assert r.json()["detail"]["excess_kwh"] == 0.01
