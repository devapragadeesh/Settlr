"""`agent_approval_requests` and `human_resolutions` (DECISIONS.md Sec.94).
Neither table is a replay of a run, so unlike `test_writer_and_queries.py`
these only need one written row against a `runs` row to satisfy the
foreign key -- not a real `resolve()`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from store.approvals import (create_approval_request, get_approval_request,
                              human_resolution, list_approval_requests,
                              record_human_resolution, resolve_approval_request)
from store.db import connect


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    conn.execute(
        "INSERT INTO runs (run_id, dataset, resolver, code_digest, input_digest, "
        "cap, time_budget, started_at, finished_at, seconds, status) "
        "VALUES ('run1', 'd', 'resolver', 'c', 'i', 40, 3.0, 't0', 't1', 1.0, 'ok')")
    conn.commit()
    yield conn
    conn.close()


def test_a_pending_request_can_be_created_and_read_back(db) -> None:
    request_id = create_approval_request(
        db, agent="break_investigator", action="reclassify", run_id="run1",
        row_ids=["r2", "r1"], proposed_change={"reason": "mapping_issue"},
        evidence_summary="ERP order found under a different id format.",
        created_at="t0")

    record = get_approval_request(db, request_id)
    assert record["status"] == "pending"
    assert record["row_ids"] == ["r1", "r2"]  # sorted on write
    assert record["proposed_change"] == {"reason": "mapping_issue"}
    assert record["resolved_at"] is None


def test_resolving_sets_status_and_cannot_be_resolved_twice(db) -> None:
    request_id = create_approval_request(
        db, agent="break_investigator", action="reclassify", run_id="run1",
        row_ids=["r1"], proposed_change={}, evidence_summary="e", created_at="t0")

    resolve_approval_request(db, request_id, status="approved",
                              resolved_by="alice", resolved_at="t1")
    record = get_approval_request(db, request_id)
    assert record["status"] == "approved"
    assert record["resolved_by"] == "alice"

    with pytest.raises(ValueError):
        resolve_approval_request(db, request_id, status="approved",
                                  resolved_by="bob", resolved_at="t2")


def test_resolving_rejects_an_invalid_status(db) -> None:
    request_id = create_approval_request(
        db, agent="a", action="x", run_id="run1", row_ids=[], proposed_change={},
        evidence_summary="e", created_at="t0")
    with pytest.raises(ValueError):
        resolve_approval_request(db, request_id, status="maybe",
                                  resolved_by="alice", resolved_at="t1")


def test_resolving_a_nonexistent_request_raises(db) -> None:
    with pytest.raises(KeyError):
        resolve_approval_request(db, "nonexistent", status="approved",
                                  resolved_by="alice", resolved_at="t1")


def test_list_filters_by_status(db) -> None:
    r1 = create_approval_request(db, agent="a", action="x", run_id="run1",
                                  row_ids=[], proposed_change={}, evidence_summary="e",
                                  created_at="t0")
    create_approval_request(db, agent="a", action="y", run_id="run1", row_ids=[],
                             proposed_change={}, evidence_summary="e", created_at="t1")
    resolve_approval_request(db, r1, status="approved", resolved_by="alice", resolved_at="t2")

    pending = list_approval_requests(db, status="pending")
    approved = list_approval_requests(db, status="approved")
    assert len(pending) == 1
    assert len(approved) == 1
    assert list_approval_requests(db) == pending + approved or len(list_approval_requests(db)) == 2


def test_human_resolution_is_recorded_separately_from_row_outcomes(db) -> None:
    resolution_id = record_human_resolution(
        db, run_id="run1", bank_index=3, chosen_candidate_row_ids=["r5", "r2"],
        rationale="Named payment matches the counterparty on the bank memo.",
        resolved_by="alice", resolved_at="t0")

    record = human_resolution(db, "run1", 3)
    assert record["resolution_id"] == resolution_id
    assert record["chosen_candidate_row_ids"] == ["r2", "r5"]

    row_outcomes_count = db.execute("SELECT COUNT(*) FROM row_outcomes").fetchone()[0]
    line_outcomes_count = db.execute("SELECT COUNT(*) FROM line_outcomes").fetchone()[0]
    assert row_outcomes_count == 0
    assert line_outcomes_count == 0


def test_human_resolution_returns_none_when_absent(db) -> None:
    assert human_resolution(db, "run1", 99) is None
