import json

from app.db import connect
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill

DEFAULT_PERIOD = "2026-08"


def _migrate(conn):
    """Idempotent schema upgrades for databases created by older versions."""
    reading_cols = [r["name"] for r in conn.execute("PRAGMA table_info(readings)").fetchall()]
    if reading_cols and "period" not in reading_cols:
        conn.execute("ALTER TABLE readings ADD COLUMN period TEXT")
        conn.execute("UPDATE readings SET period=? WHERE period IS NULL", (DEFAULT_PERIOD,))
    conn.commit()


def init_db():
    conn = connect()
    conn.executescript(
        """
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS accounts(
        id INTEGER PRIMARY KEY, name TEXT, meter_no TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS readings(
        id INTEGER PRIMARY KEY, account_id INTEGER, kwh REAL, peak INTEGER, period TEXT);
    CREATE TABLE IF NOT EXISTS tiers(id INTEGER PRIMARY KEY, up_to REAL, price REAL, sort_order INTEGER);
    CREATE TABLE IF NOT EXISTS outage_credits(
        id INTEGER PRIMARY KEY,
        account_id INTEGER NOT NULL,
        period TEXT NOT NULL,
        kwh REAL NOT NULL,
        note TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        voided_at TEXT,
        void_note TEXT
    );
    CREATE TABLE IF NOT EXISTS calc_runs(
        id INTEGER PRIMARY KEY,
        kind TEXT,
        account_id INTEGER,
        input_json TEXT,
        result_json TEXT,
        created_at TEXT
    );
    """
    )
    _migrate(conn)
    if conn.execute("SELECT COUNT(*) c FROM accounts").fetchone()["c"] == 0:
        conn.execute(
            "INSERT INTO accounts(name, meter_no, note) VALUES ('张家', 'M-1001', '对照：正常用量')"
        )
        conn.execute(
            "INSERT INTO accounts(name, meter_no, note) VALUES ('李家(种子偏高)', 'M-1002', '对照：高用量+尖峰')"
        )
        conn.executemany(
            "INSERT INTO tiers(up_to, price, sort_order) VALUES (?,?,?)",
            [(180, 0.52, 1), (260, 0.62, 2), (None, 0.82, 3)],
        )
        conn.execute(
            "INSERT INTO readings(account_id, kwh, peak, period) VALUES (1, 120, 0, ?)",
            (DEFAULT_PERIOD,),
        )
        conn.execute(
            "INSERT INTO readings(account_id, kwh, peak, period) VALUES (2, 400, 1, ?)",
            (DEFAULT_PERIOD,),
        )
        conn.execute("INSERT INTO settings(key, value) VALUES ('peak_factor', '1.2')")
        conn.execute("INSERT INTO settings(key, value) VALUES ('currency', 'CNY')")
        # 张家：一笔已作废的停电信用（保留审计行，不再参与扣除）
        conn.execute(
            """
            INSERT INTO outage_credits(account_id, period, kwh, note, status, created_at, voided_at, void_note)
            VALUES (1, ?, 20, '线路检修停电(已撤回)', 'void', datetime('now'), datetime('now'), '复核恢复供电，撤回信用')
            """,
            (DEFAULT_PERIOD,),
        )
        # 李家：两笔有效信用累加 20 + 10 = 30，毛 400 → 净 370
        conn.execute(
            "INSERT INTO outage_credits(account_id, period, kwh, note, status, created_at) VALUES (2, ?, 20, '台区停电', 'active', datetime('now'))",
            (DEFAULT_PERIOD,),
        )
        conn.execute(
            "INSERT INTO outage_credits(account_id, period, kwh, note, status, created_at) VALUES (2, ?, 10, '故障抢修停电', 'active', datetime('now'))",
            (DEFAULT_PERIOD,),
        )
        tiers = [{"up_to": r[0], "price": r[1]} for r in [(180, 0.52), (260, 0.62), (None, 0.82)]]
        bill1 = calc_bill(120, tiers, 1.0)
        conn.execute(
            "INSERT INTO calc_runs(kind, account_id, input_json, result_json, created_at) VALUES (?,?,?,?,datetime('now'))",
            ("bill", 1, json.dumps({"kwh": 120, "peak": False}), json.dumps(bill1, ensure_ascii=False)),
        )
        cmp2 = compare_plain_vs_peak(400, tiers, 1.2)
        conn.execute(
            "INSERT INTO calc_runs(kind, account_id, input_json, result_json, created_at) VALUES (?,?,?,?,datetime('now'))",
            ("compare", 2, json.dumps({"kwh": 400}), json.dumps(cmp2, ensure_ascii=False)),
        )
        conn.commit()
    conn.close()
