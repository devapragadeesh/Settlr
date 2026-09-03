from __future__ import annotations

from pathlib import Path

import pytest

from agents.itc_drafter import NoItcRisk, draft, gather_grounds, propose
from service.pipeline import run_pipeline
from store.approvals import get_approval_request
from store.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
#: A20_B50_Cmax (used by other agent tests) has zero itc_risk-flagged rows --
#: confirmed this session's dashboard GST panel finding. A10_B100_Cmax has 8.
DATASET_DIR = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"


@pytest.fixture(scope="module")
def populated_db(tmp_path_factory) -> Path:
    db_path = tmp_path_factory.mktemp("itc") / "test.db"
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
def itc_flagged_row_id(populated_db: Path, run_id: str) -> str:
    # `itc_risk` is a SUBSET of a break's `row_ids` (resolver_contract/types.py:
    # 928-930): every row belonging to a multi-row break shares the same scalar
    # `itc_risk` value, so filtering on "IS NOT NULL" alone can return a row
    # that is on the break but not itself in the flagged subset.
    conn = connect(populated_db)
    try:
        rows = conn.execute(
            "SELECT row_id, itc_risk FROM row_outcomes WHERE run_id = ? AND "
            "disposition = 'OpenBreak' AND itc_risk IS NOT NULL", (run_id,)).fetchall()
        for row in rows:
            if row["row_id"] in row["itc_risk"].split(","):
                return row["row_id"]
        raise AssertionError("fixture dataset has no row actually inside its "
                              "own itc_risk subset -- pick another")
    finally:
        conn.close()


def test_gather_grounds_on_a_real_flagged_row(
        populated_db: Path, run_id: str, itc_flagged_row_id: str) -> None:
    conn = connect(populated_db)
    try:
        facts = gather_grounds(conn, run_id, itc_flagged_row_id)
    finally:
        conn.close()
    assert facts["row_id"] == itc_flagged_row_id
    assert len(facts["grounds"]) > 0
    assert all(g in ("gstr2b_absent", "gstr2b_no_irn", "gstr2b_37a_exposure")
               for g in facts["grounds"])


def test_gather_grounds_refuses_an_unflagged_row(populated_db: Path, run_id: str) -> None:
    conn = connect(populated_db)
    try:
        unflagged = conn.execute(
            "SELECT row_id FROM row_outcomes WHERE run_id = ? AND disposition = "
            "'OpenBreak' AND itc_risk IS NULL LIMIT 1", (run_id,)).fetchone()
        row_id = unflagged["row_id"] if unflagged else "not-a-real-row"
        with pytest.raises(NoItcRisk):
            gather_grounds(conn, run_id, row_id)
    finally:
        conn.close()


def test_draft_includes_the_disclaimer_and_a_citation_for_every_ground(
        populated_db: Path, run_id: str, itc_flagged_row_id: str) -> None:
    conn = connect(populated_db)
    try:
        facts = gather_grounds(conn, run_id, itc_flagged_row_id)
    finally:
        conn.close()
    drafts = draft(facts)
    assert set(drafts) == set(facts["grounds"])
    for text in drafts.values():
        assert "does not and cannot identify which bank credit" in text


def test_propose_creates_a_pending_request_and_writes_nothing_else(
        populated_db: Path, run_id: str, itc_flagged_row_id: str) -> None:
    conn = connect(populated_db)
    try:
        before = conn.execute("SELECT COUNT(*) AS c FROM row_outcomes").fetchone()["c"]
        request_id = propose(conn, run_id, itc_flagged_row_id, created_at="t0")
        after = conn.execute("SELECT COUNT(*) AS c FROM row_outcomes").fetchone()["c"]
        record = get_approval_request(conn, request_id)
    finally:
        conn.close()

    assert before == after
    assert record["status"] == "pending"
    assert record["action"] == "itc_exposure_draft"
    assert record["row_ids"] == [itc_flagged_row_id]
