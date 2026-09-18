import sqlite3
from datetime import datetime, timezone

# 有效（参与扣除）状态；作废行保留作审计
STATUS_ACTIVE = "active"
STATUS_VOID = "void"

_LIST_COLS = (
    "id, account_id, period, kwh, reason, status, "
    "voided_at, void_reason, created_at"
)


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["active"] = d["status"] == STATUS_ACTIVE
    return d


def insert(
    conn: sqlite3.Connection,
    account_id: int,
    period: str,
    kwh: float,
    reason: str | None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO outage_credits(account_id, period, kwh, reason, status, created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (account_id, period, float(kwh), reason, STATUS_ACTIVE, now),
    )
    conn.commit()
    row = conn.execute(
        f"SELECT {_LIST_COLS} FROM outage_credits WHERE id=?", (cur.lastrowid,)
    ).fetchone()
    return _row_to_dict(row)


def list_for_account(
    conn: sqlite3.Connection, account_id: int, period: str | None = None
) -> list[dict]:
    if period is None:
        q = f"SELECT {_LIST_COLS} FROM outage_credits WHERE account_id=? ORDER BY period, id"
        rows = conn.execute(q, (account_id,)).fetchall()
    else:
        q = (
            f"SELECT {_LIST_COLS} FROM outage_credits "
            "WHERE account_id=? AND period=? ORDER BY id"
        )
        rows = conn.execute(q, (account_id, period)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get(conn: sqlite3.Connection, credit_id: int) -> dict | None:
    row = conn.execute(
        f"SELECT {_LIST_COLS} FROM outage_credits WHERE id=?", (credit_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def active_total(
    conn: sqlite3.Connection, account_id: int, period: str
) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(kwh), 0) AS total FROM outage_credits
        WHERE account_id=? AND period=? AND status=?
        """,
        (account_id, period, STATUS_ACTIVE),
    ).fetchone()
    return float(row["total"])


def void(conn: sqlite3.Connection, credit_id: int, reason: str | None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE outage_credits SET status=?, voided_at=?, void_reason=? WHERE id=?",
        (STATUS_VOID, now, reason, credit_id),
    )
    conn.commit()
    return get(conn, credit_id)
