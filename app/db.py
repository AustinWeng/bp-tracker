import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "phase2_db" / "bp.db"


def get_db_path():
    return Path(os.environ.get("BP_DB_PATH", DEFAULT_DB))


def get_db():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query(sql, params=()):
    with get_db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def execute(sql, params=()):
    with get_db() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def ensure_migrations():
    """Idempotent in-place migrations for existing bp.db files.

    Add new tables/columns introduced after the original schema here. Each
    block is guarded by IF NOT EXISTS / try-except so it's safe to re-run.
    """
    with get_db() as conn:
        # Phase 3+: user_settings (key/value) for guideline preference etc.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
                key TEXT NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id, key)
            )
        """)
        conn.commit()


def get_setting(key: str, default=None, user_id: int = 1):
    rows = query("SELECT value FROM user_settings WHERE user_id=? AND key=?", (user_id, key))
    return rows[0]["value"] if rows else default


def set_setting(key: str, value: str, user_id: int = 1):
    execute("""
        INSERT INTO user_settings(user_id, key, value, updated_at)
        VALUES(?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
    """, (user_id, key, value))
