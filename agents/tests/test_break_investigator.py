from __future__ import annotations

from pathlib import Path

import pytest

from agents.break_investigator import (NotInvestigable, draft_case_file,
                                        gather_case_facts, propose_reclassification)
from service.pipeline import run_pipeline
from store.approvals import get_approval_request
from store.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A20_B50_Cmax"


@pytest.fixture(scope="module")
def populated_db(tmp_path_factory) -> Path:
    db_path = tmp_path_factory.mktemp("investigator") / "test.db"
    conn = connect(db_path)
    run_pipeline(DATASET_DIR, conn, cap=40, time_budget=5.0)
    conn.close()
    return db_path


@pytest.fixture()
def run_id(populated_db: Path) -> str:
    conn = connect(populated_db)
    try:
        return conn.execute("SELECT run_id FROM runs LIMIT 1").fetchone()["run_id"]
    finally:
        conn.close()


@pytest.fixture()
def unexplained_row_id(populated_db: Path, run_id: str) -> str:
    conn = connect(populated_db)
    try:
        row = conn.execute(
            "SELECT row_id FROM row_outcomes WHERE run_id = ? AND disposition = "
            "'OpenBreak' AND reason = 'unexplained' LIMIT 1", (run_id,)).fetchone()
        assert row is not None, "fixture dataset has no unexplained break -- pick another"
        return row["row_id"]
    finally:
        conn.close()


def test_gather_case_facts_on_a_real_unexplained_row(
        populated_db: Path, run_id: str, unexplained_row_id: str) -> None:
    conn = connect(populated_db)
    try:
        facts = gather_case_facts(conn, run_id, unexplained_row_id)
    finally:
        conn.close()
    assert facts["row_id"] == unexplained_row_id
    assert isinstance(facts["age_days"], int)
    assert isinstance(facts["history"], list)


def test_gather_case_facts_refuses_a_non_unexplained_row(
        populated_db: Path, run_id: str) -> None:
    conn = connect(populated_db)
    try:
        verified_row = conn.execute(
            "SELECT row_id FROM row_outcomes WHERE run_id = ? AND reason != "
            "'unexplained' LIMIT 1", (run_id,)).fetchone()
        other_row_id = (verified_row["row_id"] if verified_row
                         else "definitely-not-a-real-row-id")
        with pytest.raises(NotInvestigable):
            gather_case_facts(conn, run_id, other_row_id)
    finally:
        conn.close()


def test_draft_case_file_degrades_to_a_template(unexplained_row_id: str) -> None:
    facts = {"row_id": unexplained_row_id, "age_days": 45, "first_seen": "2027-01-01",
              "itc_risk_flagged": False, "history": [],
              "classified_differently_under_another_run": False}
    text = draft_case_file(facts)
    assert unexplained_row_id in text
    assert "45" in text


def test_propose_reclassification_rejects_an_invalid_reason(
        populated_db: Path, run_id: str, unexplained_row_id: str) -> None:
    conn = connect(populated_db)
    try:
        with pytest.raises(ValueError):
            propose_reclassification(
                conn, run_id, unexplained_row_id, new_reason="not_a_real_reason",
                rationale="x", created_at="t0")
    finally:
        conn.close()


def test_propose_reclassification_creates_a_pending_request_and_writes_nothing_else(
        populated_db: Path, run_id: str, unexplained_row_id: str) -> None:
    conn = connect(populated_db)
    try:
        before = conn.execute("SELECT COUNT(*) AS c FROM row_outcomes").fetchone()["c"]
        request_id = propose_reclassification(
            conn, run_id, unexplained_row_id, new_reason="mapping_issue",
            rationale="ERP order found under a reformatted id.", created_at="t0")
        after = conn.execute("SELECT COUNT(*) AS c FROM row_outcomes").fetchone()["c"]

        record = get_approval_request(conn, request_id)
    finally:
        conn.close()

    assert before == after, "proposing a reclassification must not touch row_outcomes"
    assert record["status"] == "pending"
    assert record["action"] == "reclassify"
    assert record["proposed_change"] == {"new_reason": "mapping_issue"}
    assert record["row_ids"] == [unexplained_row_id]
