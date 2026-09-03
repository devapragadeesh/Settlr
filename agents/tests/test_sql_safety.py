from __future__ import annotations

import sqlite3

import pytest

from agents.sql_safety import UnsafeQuery, safe_select


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    c.execute("INSERT INTO t VALUES (1, 'a')")
    c.commit()
    return c


def test_a_real_select_works(conn: sqlite3.Connection) -> None:
    assert safe_select(conn, "SELECT * FROM t") == [{"id": 1, "name": "a"}]


@pytest.mark.parametrize("hostile", [
    "DROP TABLE t",
    "INSERT INTO t VALUES (2, 'x')",
    "UPDATE t SET name = 'x'",
    "DELETE FROM t",
    "SELECT * FROM t; DROP TABLE t",
    "SELECT * FROM t WHERE id = (SELECT 1); DELETE FROM t",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "PRAGMA writable_schema=1",
    "CREATE TABLE x (id INTEGER)",
    "",
    "   ",
])
def test_hostile_queries_are_rejected_and_leave_data_untouched(
        conn: sqlite3.Connection, hostile: str) -> None:
    before = conn.execute("SELECT * FROM t").fetchall()
    with pytest.raises(UnsafeQuery):
        safe_select(conn, hostile)
    after = conn.execute("SELECT * FROM t").fetchall()
    assert before == after
