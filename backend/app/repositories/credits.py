import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert(conn: sqlite3.Connection, account_id: int, period: str, kwh: float, note: str | None) -> int:
    cur = conn.execute(
        """
        INSERT INTO outage_credits(account_id, period, kwh, note, status, created_at)
        VALUES (?, ?, ?, ?, 'active', ?)
        """,
        (account_id, period, kwh, note, _now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, credit_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM outage_credits WHERE id=?", (credit_id,)).fetchone()
    return dict(row) if row else None


def list_for_account(conn: sqlite3.Connection, account_id: int, period: str | None = None) -> list[dict]:
    if period is None:
        q = "SELECT * FROM outage_credits WHERE account_id=? ORDER BY period, id"
        rows = conn.execute(q, (account_id,)).fetchall()
    else:
        q = "SELECT * FROM outage_credits WHERE account_id=? AND period=? ORDER BY id"
        rows = conn.execute(q, (account_id, period)).fetchall()
    return [dict(r) for r in rows]


def active_sum(conn: sqlite3.Connection, account_id: int, period: str) -> float:
    """Sum of non-voided credits for an account-period (0 when none)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(kwh), 0) s FROM outage_credits WHERE account_id=? AND period=? AND status='active'",
        (account_id, period),
    ).fetchone()
    return float(row["s"])


def void(conn: sqlite3.Connection, credit_id: int, note: str | None) -> None:
    conn.execute(
        """
        UPDATE outage_credits
        SET status='void', voided_at=?, void_note=?
        WHERE id=?
        """,
        (_now(), note, credit_id),
    )
    conn.commit()
