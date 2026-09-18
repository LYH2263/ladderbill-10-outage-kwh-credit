import sqlite3


def list_all(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM readings ORDER BY id").fetchall()]


def for_account(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    q = "SELECT * FROM readings WHERE account_id=? ORDER BY period, id"
    return [dict(r) for r in conn.execute(q, (account_id,)).fetchall()]


def periods_for_account(conn: sqlite3.Connection, account_id: int) -> list[str]:
    """Distinct billing periods that have readings, newest first."""
    q = """
    SELECT DISTINCT period FROM readings
    WHERE account_id=? AND period IS NOT NULL
    ORDER BY period DESC
    """
    return [r["period"] for r in conn.execute(q, (account_id,)).fetchall()]


def period_totals(conn: sqlite3.Connection, account_id: int, period: str) -> dict | None:
    """Gross kWh and peak flag of an account-period; None when no reading exists."""
    row = conn.execute(
        "SELECT COALESCE(SUM(kwh), 0) s, COUNT(*) n, COALESCE(MAX(peak), 0) p FROM readings WHERE account_id=? AND period=?",
        (account_id, period),
    ).fetchone()
    if row["n"] == 0:
        return None
    return {"gross_kwh": float(row["s"]), "peak": int(row["p"])}
