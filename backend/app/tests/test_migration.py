from app import seed
from app.db import DB_PATH, connect


def test_legacy_db_without_period_column_is_migrated():
    """An old database (readings without period, no outage_credits) upgrades in place."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE accounts(id INTEGER PRIMARY KEY, name TEXT, meter_no TEXT, note TEXT);
        CREATE TABLE readings(id INTEGER PRIMARY KEY, account_id INTEGER, kwh REAL, peak INTEGER);
        INSERT INTO accounts(name, meter_no, note) VALUES ('老户', 'M-OLD', '');
        INSERT INTO readings(account_id, kwh, peak) VALUES (1, 88, 0);
        """
    )
    conn.commit()
    conn.close()

    seed.init_db()  # accounts 非空 → 只迁移、不播种

    conn = connect()
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(readings)").fetchall()]
    assert "period" in cols
    period = conn.execute("SELECT period FROM readings WHERE id=1").fetchone()["period"]
    assert period == seed.DEFAULT_PERIOD
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "outage_credits" in tables
    conn.close()
