"""`run_pipeline` against a real corpus dataset and a real SQLite file:
idempotent re-run, and the digests it computes actually change when they
should."""

from __future__ import annotations

from pathlib import Path

from service.pipeline import code_digest, input_digest, run_pipeline
from store.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"


def test_run_pipeline_writes_a_run_and_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "test.db")
    try:
        run_id_1 = run_pipeline(DATASET_DIR, conn, cap=40, time_budget=3.0)
        run_id_2 = run_pipeline(DATASET_DIR, conn, cap=40, time_budget=3.0)
        assert run_id_1 == run_id_2

        count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_a_different_cap_produces_a_different_run(tmp_path: Path) -> None:
    conn = connect(tmp_path / "test.db")
    try:
        run_id_1 = run_pipeline(DATASET_DIR, conn, cap=40, time_budget=3.0)
        run_id_2 = run_pipeline(DATASET_DIR, conn, cap=41, time_budget=3.0)
        assert run_id_1 != run_id_2
        count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_input_digest_changes_when_a_file_changes(tmp_path: Path) -> None:
    staged = tmp_path / "dataset"
    staged.mkdir()
    for name in ("recon_combined.json", "bank_statement.csv"):
        (staged / name).write_text((DATASET_DIR / name).read_text())

    before = input_digest(staged)
    (staged / "bank_statement.csv").write_text(
        (DATASET_DIR / "bank_statement.csv").read_text() + "\n")
    after = input_digest(staged)
    assert before != after


def test_code_digest_is_stable_across_calls() -> None:
    assert code_digest() == code_digest()
