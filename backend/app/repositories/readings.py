import sqlite3


def list_all(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM readings ORDER BY id").fetchall()]


def for_account(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    q = "SELECT * FROM readings WHERE account_id=? ORDER BY id"
    return [dict(r) for r in conn.execute(q, (account_id,)).fetchall()]


def latest_kwh(conn: sqlite3.Connection, account_id: int) -> float | None:
    """该户最近一次抄表电量，作为信用登记/扣减使用的账期毛电量。"""
    row = conn.execute(
        "SELECT kwh FROM readings WHERE account_id=? ORDER BY id DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    return float(row["kwh"]) if row else None
