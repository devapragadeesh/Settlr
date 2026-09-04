"""`write_run` -> `store/queries.py` round-trip, idempotency on `run_id`, and
`row_history` across a break that opens then closes.

`resolve()` is expensive (a real CP-SAT solve per credit line), so this file
resolves ONE small dataset ONCE per test session (module-scoped fixture) and
reuses that `ResolverOutput` across every test that doesn't need a second,
different run.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ingest import load
from resolver.resolve import resolve
from resolver_contract.types import ResolverOutput
from store.db import connect
from store.queries import (break_lifecycle, get_run, line_outcome,
                            line_summaries, open_break_detail, open_breaks,
                            owner_for_reason, read_resolver_output, row_history,
                            row_outcome, runs_for_dataset, sources_for_run,
                            valid_break_reasons)
from store.writer import compute_run_id, write_run

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"


@pytest.fixture(scope="module")
def resolved_output() -> ResolverOutput:
    dataset = load(DATASET_DIR)
    return resolve(dataset, cap=40, time_budget=3.0)


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    yield conn
    conn.close()


def _all_row_ids(directory: Path) -> frozenset[str]:
    dataset = load(directory)
    return frozenset(row["entity_id"] for row in dataset.rows)


def test_write_then_read_back_is_lossless(db, resolved_output) -> None:
    run_id = write_run(db, resolved_output, all_row_ids=_all_row_ids(DATASET_DIR),
                        cap=40, time_budget=3.0, input_digest="in1",
                        code_digest="code1", started_at="2027-01-01T00:00:00Z",
                        finished_at="2027-01-01T00:00:05Z", seconds=5.0)

    restored = read_resolver_output(db, run_id)
    assert restored == resolved_output


def test_run_id_is_derived_and_deterministic(db, resolved_output) -> None:
    all_ids = _all_row_ids(DATASET_DIR)
    run_id_1 = write_run(db, resolved_output, all_row_ids=all_ids, cap=40,
                          time_budget=3.0, input_digest="in1", code_digest="code1",
                          started_at="t0", finished_at="t1", seconds=1.0)
    expected = compute_run_id(input_digest="in1", code_digest="code1", cap=40,
                               time_budget=3.0)
    assert run_id_1 == expected


def test_rewriting_the_same_inputs_is_a_no_op_not_a_duplicate(db, resolved_output) -> None:
    all_ids = _all_row_ids(DATASET_DIR)
    kwargs = dict(all_row_ids=all_ids, cap=40, time_budget=3.0,
                   input_digest="in1", code_digest="code1",
                   started_at="t0", finished_at="t1", seconds=1.0)
    run_id_1 = write_run(db, resolved_output, **kwargs)
    run_id_2 = write_run(db, resolved_output, **kwargs)
    assert run_id_1 == run_id_2

    count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    assert count == 1

    line_count = db.execute(
        "SELECT COUNT(*) FROM line_outcomes WHERE run_id = ?", (run_id_1,)
    ).fetchone()[0]
    assert line_count == len(resolved_output.line_outcomes)


def test_a_different_cap_produces_a_different_run_id(db, resolved_output) -> None:
    all_ids = _all_row_ids(DATASET_DIR)
    run_id_1 = write_run(db, resolved_output, all_row_ids=all_ids, cap=40,
                          time_budget=3.0, input_digest="in1", code_digest="code1",
                          started_at="t0", finished_at="t1", seconds=1.0)
    run_id_2 = write_run(db, resolved_output, all_row_ids=all_ids, cap=41,
                          time_budget=3.0, input_digest="in1", code_digest="code1",
                          started_at="t0", finished_at="t1", seconds=1.0)
    assert run_id_1 != run_id_2


def test_get_run_and_line_outcome_and_row_outcome(db, resolved_output) -> None:
    all_ids = _all_row_ids(DATASET_DIR)
    run_id = write_run(db, resolved_output, all_row_ids=all_ids, cap=40,
                        time_budget=3.0, input_digest="in1", code_digest="code1",
                        started_at="t0", finished_at="t1", seconds=1.0)

    run = get_run(db, run_id)
    assert run["dataset"] == resolved_output.dataset
    assert run["resolver"] == resolved_output.resolver

    first = resolved_output.line_outcomes[0]
    assert line_outcome(db, run_id, first.bank_index) == first

    if resolved_output.unmatched:
        target = resolved_output.unmatched[0]
        got = row_outcome(db, run_id, target.row_ids[0])
        assert got == target


def test_open_breaks_are_bucketed_by_age(db, resolved_output) -> None:
    all_ids = _all_row_ids(DATASET_DIR)
    run_id = write_run(db, resolved_output, all_row_ids=all_ids, cap=40,
                        time_budget=3.0, input_digest="in1", code_digest="code1",
                        started_at="t0", finished_at="t1", seconds=1.0)

    buckets = open_breaks(db, run_id)
    from resolver_contract.types import AGE_BUCKETS
    assert set(buckets) == {name for name, _, _ in AGE_BUCKETS}

    total_bucketed = sum(len(rows) for rows in buckets.values())
    # One row_outcomes row per row_id, not per outcome object -- an OpenBreak
    # can bundle several row_ids (clustered rows sharing one cause), so the
    # comparison is against total ROW IDS across OpenBreak outcomes.
    actual_open_break_row_ids = sum(
        len(o.row_ids) for o in resolved_output.unmatched
        if type(o).__name__ == "OpenBreak")
    assert total_bucketed == actual_open_break_row_ids


def test_row_history_across_a_break_opening_then_closing(db) -> None:
    """A synthetic two-run scenario (not from resolve() -- constructed
    directly against the ResolverOutput/OpenBreak dataclasses) proving the
    actual payoff of Track C: `investigation/CONTROLS_MAPPING.md` Sec.3(b)
    names 'no log of an outcome changing... as new evidence arrived' as
    absent. This test is that log, read back."""
    from resolver_contract.types import (BreakReason, Evidence, EvidenceKind,
                                          IndependenceDetermination,
                                          OpenBreak, SourceSystem, Verified,
                                          Composition, Warrant)

    break_warrant = Warrant(
        evidence=(Evidence(kind=EvidenceKind.BANK_REFERENCE,
                            derived_from=frozenset({SourceSystem.BANK}),
                            detail="ref"),),
        independence=IndependenceDetermination(
            sources=frozenset({SourceSystem.BANK}), rationale="single source"))

    run1_output = ResolverOutput(
        resolver="test", dataset="synthetic",
        line_outcomes=(),
        unmatched=(OpenBreak(row_ids=("pay_X",), reason=BreakReason.TIMING_DIFFERENCE,
                              age_days=5, first_seen="2027-01-01",
                              warrant=break_warrant),))

    run1_id = write_run(db, run1_output, all_row_ids=frozenset({"pay_X"}),
                         cap=40, time_budget=3.0, input_digest="d1",
                         code_digest="c1", started_at="2027-01-01T00:00:00Z",
                         finished_at="2027-01-01T00:00:01Z", seconds=1.0)

    composition = Composition(credit_ids=("pay_X",), debit_ids=(),
                               credit_total=100, debit_total=0)
    composition_warrant = Warrant(
        evidence=(Evidence(kind=EvidenceKind.ATTESTED_SETTLEMENT_ID,
                            derived_from=frozenset({SourceSystem.PSP_LEDGER}),
                            detail="settlement_id", supports=("pay_X",)),
                  Evidence(kind=EvidenceKind.BANK_REFERENCE,
                            derived_from=frozenset({SourceSystem.BANK}),
                            detail="bank credit exists"),
                  Evidence(kind=EvidenceKind.ARITHMETIC_CLOSURE,
                            derived_from=frozenset({SourceSystem.RESOLVER_INTERNAL}),
                            detail="sums to the credit")),
        independence=IndependenceDetermination(
            sources=frozenset({SourceSystem.PSP_LEDGER, SourceSystem.BANK,
                                SourceSystem.RESOLVER_INTERNAL}),
            rationale="PSP settlement id plus an independent bank credit, "
                      "plus the resolver's own arithmetic"))
    run2_output = ResolverOutput(
        resolver="test", dataset="synthetic",
        line_outcomes=(Verified(bank_index=0, composition=composition,
                                 warrant=composition_warrant,
                                 rival_closure_count=1),),
        unmatched=())

    write_run(db, run2_output, all_row_ids=frozenset({"pay_X"}),
              cap=40, time_budget=3.0, input_digest="d2", code_digest="c1",
              started_at="2027-01-02T00:00:00Z",
              finished_at="2027-01-02T00:00:01Z", seconds=1.0)

    history = row_history(db, "synthetic", "pay_X")
    assert [h["state"] for h in history] == ["OpenBreak", "Verified"]

    lifecycle = break_lifecycle(db, "pay_X")
    assert lifecycle["first_run_id"] == run1_id
    assert lifecycle["closed_at"] is not None


def test_line_summaries_omit_outcome_json_and_cover_every_line(db, resolved_output) -> None:
    run_id = write_run(db, resolved_output, all_row_ids=_all_row_ids(DATASET_DIR),
                        cap=40, time_budget=3.0, input_digest="ls1", code_digest="c1",
                        started_at="t0", finished_at="t1", seconds=1.0)
    summaries = line_summaries(db, run_id)
    assert len(summaries) == len(resolved_output.line_outcomes)
    assert set(summaries[0]) == {"bank_index", "kind", "reason",
                                 "rival_closure_count", "candidate_count", "detail"}


def test_sources_for_run_returns_what_write_run_was_given(db, resolved_output) -> None:
    sources = [{"artifact_path": "bank_statement.csv", "source_system": "unknown",
                "format": "csv", "sha256": "abc123"}]
    run_id = write_run(db, resolved_output, all_row_ids=_all_row_ids(DATASET_DIR),
                        cap=40, time_budget=3.0, input_digest="sr1", code_digest="c1",
                        started_at="t0", finished_at="t1", seconds=1.0, sources=sources)
    recorded = sources_for_run(db, run_id)
    assert len(recorded) == 1
    assert recorded[0]["artifact_path"] == "bank_statement.csv"


def test_open_break_detail_matches_a_row_from_open_breaks(db, resolved_output) -> None:
    run_id = write_run(db, resolved_output, all_row_ids=_all_row_ids(DATASET_DIR),
                        cap=40, time_budget=3.0, input_digest="obd1", code_digest="c1",
                        started_at="t0", finished_at="t1", seconds=1.0)
    buckets = open_breaks(db, run_id)
    any_row = next((r for rows in buckets.values() for r in rows), None)
    if any_row is None:
        pytest.skip("fixture dataset has no open breaks")
    detail = open_break_detail(db, run_id, any_row["row_id"])
    assert detail["reason"] == any_row["reason"]
    assert detail["age_days"] == any_row["age_days"]
    assert open_break_detail(db, run_id, "not-a-real-row") is None


def test_valid_break_reasons_and_owner_for_reason_match_the_live_contract() -> None:
    reasons = valid_break_reasons()
    assert reasons == tuple(sorted(reasons))  # sorted, per its own docstring
    assert "unexplained" in reasons
    assert "timing_difference" in reasons
    owner, close_condition = owner_for_reason("timing_difference")
    assert owner == "none -- carry forward"
    assert "later window" in close_condition
