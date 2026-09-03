from __future__ import annotations

from pathlib import Path

import pytest

from agents.ambiguous_arbiter import (NotAmbiguous, draft_comparison, present,
                                       record_resolution)
from service.pipeline import run_pipeline
from store.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A20_B50_Cmax"


@pytest.fixture(scope="module")
def populated_db(tmp_path_factory) -> Path:
    db_path = tmp_path_factory.mktemp("arbiter") / "test.db"
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
def ambiguous_bank_index(populated_db: Path, run_id: str) -> int:
    conn = connect(populated_db)
    try:
        row = conn.execute(
            "SELECT bank_index FROM line_outcomes WHERE run_id = ? AND kind = "
            "'Ambiguous' LIMIT 1", (run_id,)).fetchone()
        assert row is not None, "fixture dataset has no Ambiguous line -- pick another"
        return row["bank_index"]
    finally:
        conn.close()


def test_present_returns_at_least_two_real_candidates(
        populated_db: Path, run_id: str, ambiguous_bank_index: int) -> None:
    conn = connect(populated_db)
    try:
        presentation = present(conn, run_id, ambiguous_bank_index)
    finally:
        conn.close()
    assert presentation["candidate_count"] >= 2
    assert len(presentation["candidates"]) == presentation["candidate_count"]


def test_present_refuses_a_non_ambiguous_line(populated_db: Path, run_id: str) -> None:
    conn = connect(populated_db)
    try:
        non_ambiguous = conn.execute(
            "SELECT bank_index FROM line_outcomes WHERE run_id = ? AND kind != "
            "'Ambiguous' LIMIT 1", (run_id,)).fetchone()
        with pytest.raises(NotAmbiguous):
            present(conn, run_id, non_ambiguous["bank_index"])
    finally:
        conn.close()


def test_draft_comparison_degrades_to_a_listing(
        populated_db: Path, run_id: str, ambiguous_bank_index: int) -> None:
    conn = connect(populated_db)
    try:
        presentation = present(conn, run_id, ambiguous_bank_index)
    finally:
        conn.close()
    text = draft_comparison(presentation)
    assert str(presentation["candidate_count"]) in text


def test_recording_a_real_candidate_writes_only_to_human_resolutions(
        populated_db: Path, run_id: str, ambiguous_bank_index: int) -> None:
    conn = connect(populated_db)
    try:
        presentation = present(conn, run_id, ambiguous_bank_index)
        chosen = presentation["candidates"][0]
        chosen_ids = chosen["credit_ids"] + chosen["debit_ids"]

        before_line = conn.execute(
            "SELECT outcome_json FROM line_outcomes WHERE run_id = ? AND "
            "bank_index = ?", (run_id, ambiguous_bank_index)).fetchone()["outcome_json"]

        resolution_id = record_resolution(
            conn, run_id, ambiguous_bank_index, chosen_candidate_row_ids=chosen_ids,
            rationale="Named payment matches the bank memo.", resolved_by="alice",
            resolved_at="t0")

        after_line = conn.execute(
            "SELECT outcome_json FROM line_outcomes WHERE run_id = ? AND "
            "bank_index = ?", (run_id, ambiguous_bank_index)).fetchone()["outcome_json"]
    finally:
        conn.close()

    assert before_line == after_line, "the Ambiguous line itself must be untouched"
    assert resolution_id


def test_recording_a_fabricated_candidate_is_rejected(
        populated_db: Path, run_id: str, ambiguous_bank_index: int) -> None:
    conn = connect(populated_db)
    try:
        with pytest.raises(ValueError):
            record_resolution(
                conn, run_id, ambiguous_bank_index,
                chosen_candidate_row_ids=["this-row-id-does-not-exist"],
                rationale="x", resolved_by="alice", resolved_at="t0")
    finally:
        conn.close()
