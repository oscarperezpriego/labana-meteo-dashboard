"""Almacén SQLite de lecturas meteorológicas en formato largo (timestamp, variable, value)."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "meteo.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    timestamp TEXT NOT NULL,
    variable TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (timestamp, variable)
);
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def upsert_readings(conn: sqlite3.Connection, long_df) -> int:
    """Inserta lecturas nuevas (timestamp, variable, value). Ignora duplicados ya guardados."""
    rows = list(long_df[["timestamp", "variable", "value"]].itertuples(index=False, name=None))
    cur = conn.executemany(
        "INSERT OR IGNORE INTO readings (timestamp, variable, value) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    return cur.rowcount
