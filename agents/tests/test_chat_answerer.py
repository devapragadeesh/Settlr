"""No API key is configured here, so every test below exercises the
deterministic fallback path -- which is the point: `ChatAnswerer` must answer
correctly (or say plainly that it can't) with zero live model calls, per
DECISIONS.md Sec.94's "an unavailable model must never change what the agent
does" carried over from Sec.11.

`test_a_hostile_model_response_cannot_write_to_the_store` is the adversarial
test Phase 0 committed to: it does not wait for Claude to actually be hostile
-- it substitutes a fake that IS, and proves the real database is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents import chat_answerer as chat_answerer_module
from agents.chat_answerer import ChatAnswerer
from service.pipeline import run_pipeline
from store.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"


@pytest.fixture(scope="module")
def populated_db(tmp_path_factory) -> Path:
    db_path = tmp_path_factory.mktemp("chat") / "test.db"
    conn = connect(db_path)
    run_pipeline(DATASET_DIR, conn, cap=40, time_budget=3.0)
    conn.close()
    return db_path


@pytest.fixture()
def run_id(populated_db: Path) -> str:
    conn = connect(populated_db)
    try:
        row = conn.execute("SELECT run_id FROM runs LIMIT 1").fetchone()
        return row["run_id"]
    finally:
        conn.close()


def _table_counts(conn) -> dict[str, int]:
    tables = ["runs", "line_outcomes", "row_outcomes", "break_history"]
    return {t: conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
            for t in tables}


def test_fallback_answers_open_breaks_with_a_real_count(
        populated_db: Path, run_id: str) -> None:
    conn = connect(populated_db)
    try:
        result = ChatAnswerer().ask(conn, run_id, "how many open breaks are there?")
    finally:
        conn.close()
    assert result["mode"] == "fallback"
    assert result["sql"] is None
    assert isinstance(result["rows"], list)
    assert str(len(result["rows"])) in result["answer"]


def test_fallback_says_it_cannot_answer_an_unrelated_question(
        populated_db: Path, run_id: str) -> None:
    conn = connect(populated_db)
    try:
        result = ChatAnswerer().ask(conn, run_id, "what is the weather today?")
    finally:
        conn.close()
    assert result["mode"] == "fallback"
    # The contract under test is the honest degrade: when the model is
    # unreachable AND the question matches none of the deterministic
    # patterns, the answer must ADMIT it cannot answer rather than guess.
    # Asserting one exact sentence pinned the copy instead of the contract
    # -- this text is user-facing (it renders in the dashboard's Ask panel)
    # and was reworded once already for that reason. Assert the admission
    # and the absence of an answer, not the wording.
    assert result["rows"] == []
    answer = result["answer"].lower()
    assert any(marker in answer for marker in
               ("could not answer", "cannot answer", "can only answer", "offline")), answer


def test_a_hostile_model_response_cannot_write_to_the_store(
        populated_db: Path, run_id: str, monkeypatch) -> None:
    hostile_sql = "DELETE FROM row_outcomes; SELECT 1"

    def fake_call_claude(system: str, user: str, *, model: str = "claude-sonnet-5") -> str:
        return hostile_sql

    monkeypatch.setattr(chat_answerer_module, "call_claude", fake_call_claude)

    conn = connect(populated_db)
    try:
        before = _table_counts(conn)
        result = ChatAnswerer().ask(conn, run_id, "delete everything")
        after = _table_counts(conn)
    finally:
        conn.close()

    assert before == after, "a hostile model response mutated the store"
    assert result["mode"] == "fallback"


def test_a_hostile_model_response_naming_a_single_write_statement_is_also_blocked(
        populated_db: Path, run_id: str, monkeypatch) -> None:
    def fake_call_claude(system: str, user: str, *, model: str = "claude-sonnet-5") -> str:
        return "DROP TABLE runs"

    monkeypatch.setattr(chat_answerer_module, "call_claude", fake_call_claude)

    conn = connect(populated_db)
    try:
        before = _table_counts(conn)
        result = ChatAnswerer().ask(conn, run_id, "drop everything")
        after = _table_counts(conn)
    finally:
        conn.close()

    assert before == after
    assert result["mode"] == "fallback"
