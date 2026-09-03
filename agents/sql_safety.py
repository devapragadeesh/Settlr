"""The one thing standing between an LLM-generated SQL string and a live
database: this must hold even when the model is actively hostile, not just
malformed, because `agents/chat_answerer.py` executes whatever it returns.

Two independent layers, so one bypassing the other still fails closed:
1. Text-level rejection of anything but a single `SELECT` statement.
2. `sqlite3.Connection.set_authorizer` -- SQLite's own callback, invoked for
   every action the *executed* statement attempts, denying everything except
   reads. A statement that smuggles a write past layer 1 (a comment, a
   trailing clause) is still denied here, because the authorizer inspects
   what SQLite is actually about to do, not the source text.
"""

from __future__ import annotations

import sqlite3

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
}


class UnsafeQuery(Exception):
    """A generated query was rejected before or during execution."""


def _authorizer(action, arg1, arg2, dbname, source):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _reject_if_unsafe(sql: str) -> None:
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    if len(statements) != 1:
        raise UnsafeQuery("exactly one statement is allowed")
    if not statements[0].lower().startswith("select"):
        raise UnsafeQuery("only SELECT is allowed")


def safe_select(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    """Execute `sql`, which must be a single `SELECT`, under an authorizer
    that denies every action but reading. Raises `UnsafeQuery` and touches
    the database not at all if the text or the live statement attempts
    anything else."""
    _reject_if_unsafe(sql)
    conn.set_authorizer(_authorizer)
    try:
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
    except sqlite3.DatabaseError as exc:
        raise UnsafeQuery(f"rejected by the database: {exc}") from exc
    finally:
        conn.set_authorizer(None)
    return [dict(row) for row in rows]
