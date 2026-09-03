from __future__ import annotations

from pathlib import Path

import pytest

from agents.sla_watchdog import Escalation, build_escalations, draft_message, run
from service.pipeline import run_pipeline
from store.db import connect
from store.queries import open_breaks

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A20_B50_Cmax"


@pytest.fixture(scope="module")
def populated_db(tmp_path_factory) -> Path:
    db_path = tmp_path_factory.mktemp("sla") / "test.db"
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


def test_escalations_never_include_timing_difference(populated_db: Path, run_id: str) -> None:
    conn = connect(populated_db)
    try:
        escalations = build_escalations(conn, run_id)
    finally:
        conn.close()
    assert all(e.reason != "timing_difference" for e in escalations)


def test_escalation_row_counts_match_open_breaks_exactly(populated_db: Path, run_id: str) -> None:
    conn = connect(populated_db)
    try:
        escalations = build_escalations(conn, run_id)
        buckets = open_breaks(conn, run_id)
    finally:
        conn.close()

    real_counts: dict[tuple[str, str], int] = {}
    for bucket_name, rows in buckets.items():
        for row in rows:
            key = (row["reason"], bucket_name)
            real_counts[key] = real_counts.get(key, 0) + 1

    for escalation in escalations:
        key = (escalation.reason, escalation.age_bucket)
        assert escalation.count == real_counts[key]


def test_draft_message_degrades_to_a_template_with_no_api_key() -> None:
    escalation = Escalation(reason="unexplained", age_bucket="61-90", level="escalate",
                             owner="investigation", close_condition="-- no close condition is known",
                             row_ids=("r1", "r2"))
    message = draft_message(escalation)
    assert "unexplained" in message
    assert "2" in message
    assert "investigation" in message


def test_run_delivers_every_escalation_through_the_notifier(populated_db: Path, run_id: str) -> None:
    delivered: list[str] = []
    conn = connect(populated_db)
    try:
        escalations = run(conn, run_id, notifier=delivered.append)
    finally:
        conn.close()
    assert len(delivered) == len(escalations)
