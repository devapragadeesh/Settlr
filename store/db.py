"""SQLite connection + a tiny forward-only migrator. No Alembic, no ORM --
`store/schema.sql` is the one source of truth for the schema, and `connect`
applies it idempotently (every `CREATE TABLE` is `IF NOT EXISTS`).

SQLite, not Postgres: a cold clone must keep working with no service to
start, which is this repo's own standing property (`README.md`'s "Run it"
section, `CLAUDE.md`'s commands). The schema is plain SQL with no
SQLite-specific syntax beyond `AUTOINCREMENT`-free integer primary keys, so a
future move to Postgres is a driver swap, not a rewrite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
CURRENT_VERSION = 2  # 2: agent_approval_requests, human_resolutions (Sec.94)


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (CURRENT_VERSION,))
    conn.commit()
