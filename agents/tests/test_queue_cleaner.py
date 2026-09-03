from __future__ import annotations

from pathlib import Path

import pytest

from agents.queue_cleaner import group_carry_forward
from service.pipeline import run_pipeline
from store.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A20_B50_Cmax"


@pytest.fixture(scope="module")
def populated_db(tmp_path_factory) -> Path:
    db_path = tmp_path_factory.mktemp("queue") / "test.db"
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


def test_grouping_partitions_every_timing_difference_row_exactly_once(
        populated_db: Path, run_id: str) -> None:
    conn = connect(populated_db)
    try:
        result = group_carry_forward(conn, run_id)
    finally:
        conn.close()

    partitioned = len(result["provable_within_window"]) + len(result["not_provable_within_window"])
    assert partitioned == result["total"]

    provable_ids = {r["row_id"] for r in result["provable_within_window"]}
    not_provable_ids = {r["row_id"] for r in result["not_provable_within_window"]}
    assert provable_ids.isdisjoint(not_provable_ids)


def test_nothing_is_closed_or_written(populated_db: Path, run_id: str) -> None:
    conn = connect(populated_db)
    try:
        before = conn.execute("SELECT COUNT(*) AS c FROM row_outcomes").fetchone()["c"]
        group_carry_forward(conn, run_id)
        after = conn.execute("SELECT COUNT(*) AS c FROM row_outcomes").fetchone()["c"]
    finally:
        conn.close()
    assert before == after
