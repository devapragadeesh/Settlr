"""`ResolverOutput` -> SQLite rows, in one transaction.

**Run identity is derived, not generated.** `run_id = sha256(input_digest ||
code_digest || cap || time_budget)` -- identical inputs and identical code
produce the identical `run_id`, which doubles as the write-side idempotency
key: `write_run` on an already-present `run_id` is a no-op, not a duplicate
row. Wall clock lives only in `runs.started_at`/`finished_at`, as DATA in one
table -- never in a `LineOutcome`/`RowOutcome`, which stay exactly as
wall-clock-free as `resolve()` itself already is.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Iterable

from resolver_contract.types import (Ambiguous, AttestationDiscrepancy,
                                      CorrectlyUnmatched, OpenBreak,
                                      ProvenUnmatched, Reconstructed,
                                      ResolverOutput, Unresolved, Verified)
from store.codec import outcome_to_jsonable


def compute_run_id(*, input_digest: str, code_digest: str, cap: int,
                    time_budget: float) -> str:
    material = f"{input_digest}|{code_digest}|{cap}|{time_budget}".encode()
    return hashlib.sha256(material).hexdigest()


def _line_outcome_row(outcome) -> dict:
    base = dict(kind=type(outcome).__name__, reason=None, pool_size=None,
                rival_closure_count=None, rival_count_is_lower_bound=None,
                candidate_count=None, candidate_complete=None,
                enumeration_cap=None, nearest_residual=None, detail=None)
    if isinstance(outcome, Verified):
        base.update(rival_closure_count=outcome.rival_closure_count,
                     rival_count_is_lower_bound=int(outcome.rival_count_is_lower_bound))
    elif isinstance(outcome, AttestationDiscrepancy):
        base.update(reason=outcome.contradiction.kind.value,
                     detail=outcome.contradiction.detail)
    elif isinstance(outcome, Reconstructed):
        pass
    elif isinstance(outcome, Ambiguous):
        base.update(candidate_count=outcome.candidate_set.size,
                     candidate_complete=int(outcome.candidate_set.complete),
                     enumeration_cap=outcome.candidate_set.enumeration_cap)
    elif isinstance(outcome, Unresolved):
        base.update(reason=outcome.reason.value, pool_size=outcome.pool_size,
                     detail=outcome.detail, nearest_residual=outcome.nearest_residual,
                     candidate_count=(outcome.partial_candidates.size
                                      if outcome.partial_candidates else None))
    else:
        raise TypeError(f"unhandled LineOutcome type: {type(outcome).__name__}")
    return base


def _row_outcome_rows(outcome) -> Iterable[tuple[str, dict]]:
    base = dict(disposition=type(outcome).__name__, reason=None, age_days=None,
                first_seen=None, caused_by=None, provable_within_window=None,
                itc_risk=None)
    if isinstance(outcome, (ProvenUnmatched, CorrectlyUnmatched)):
        base.update(reason=outcome.reason.value)
    elif isinstance(outcome, OpenBreak):
        base.update(reason=outcome.reason.value, age_days=outcome.age_days,
                     first_seen=outcome.first_seen, caused_by=outcome.caused_by,
                     provable_within_window=int(outcome.provable_within_window),
                     itc_risk=",".join(sorted(outcome.itc_risk)) or None)
    else:
        raise TypeError(f"unhandled RowOutcome type: {type(outcome).__name__}")
    for row_id in outcome.row_ids:
        yield row_id, base


def write_run(conn: sqlite3.Connection, output: ResolverOutput, *,
              all_row_ids: frozenset[str], cap: int, time_budget: float,
              input_digest: str, code_digest: str, started_at: str,
              finished_at: str, seconds: float, status: str = "ok",
              sources: list[dict] | None = None) -> str:
    run_id = compute_run_id(input_digest=input_digest, code_digest=code_digest,
                             cap=cap, time_budget=time_budget)

    existing = conn.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if existing:
        return run_id  # identical inputs and code -> no-op, not a duplicate

    conn.execute(
        "INSERT INTO runs (run_id, dataset, resolver, code_digest, input_digest, "
        "cap, time_budget, started_at, finished_at, seconds, status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, output.dataset, output.resolver, code_digest, input_digest,
         cap, time_budget, started_at, finished_at, seconds, status))

    for source in (sources or []):
        conn.execute(
            "INSERT INTO sources (run_id, artifact_path, source_system, format, "
            "sha256, fetched_at, transport) VALUES (?,?,?,?,?,?,?)",
            (run_id, source["artifact_path"], source["source_system"],
             source["format"], source["sha256"], source.get("fetched_at"),
             source.get("transport")))

    for outcome in output.line_outcomes:
        row = _line_outcome_row(outcome)
        conn.execute(
            "INSERT INTO line_outcomes (run_id, bank_index, kind, reason, "
            "pool_size, rival_closure_count, rival_count_is_lower_bound, "
            "candidate_count, candidate_complete, enumeration_cap, "
            "nearest_residual, detail, outcome_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, outcome.bank_index, row["kind"], row["reason"],
             row["pool_size"], row["rival_closure_count"],
             row["rival_count_is_lower_bound"], row["candidate_count"],
             row["candidate_complete"], row["enumeration_cap"],
             row["nearest_residual"], row["detail"],
             json.dumps(outcome_to_jsonable(outcome))))

    open_break_row_ids: set[str] = set()
    for outcome in output.unmatched:
        if isinstance(outcome, OpenBreak):
            open_break_row_ids.update(outcome.row_ids)
        for row_id, row in _row_outcome_rows(outcome):
            conn.execute(
                "INSERT INTO row_outcomes (run_id, row_id, disposition, reason, "
                "age_days, first_seen, caused_by, provable_within_window, "
                "itc_risk, outcome_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run_id, row_id, row["disposition"], row["reason"],
                 row["age_days"], row["first_seen"], row["caused_by"],
                 row["provable_within_window"], row["itc_risk"],
                 json.dumps(outcome_to_jsonable(outcome))))

    _record_break_history(conn, run_id=run_id, started_at=started_at,
                           all_row_ids=all_row_ids,
                           open_break_row_ids=open_break_row_ids)

    conn.commit()
    return run_id


def _record_break_history(conn: sqlite3.Connection, *, run_id: str,
                           started_at: str, all_row_ids: frozenset[str],
                           open_break_row_ids: set[str]) -> None:
    """Scoped by `row_id` alone, not by dataset -- a real deployment ingesting
    more than one merchant's data would need `(dataset, row_id)` as the key.
    Not needed here: `entity_id` is engine-generated as an opaque, effectively
    unique identifier (`engine/tests/test_no_leakage.py` treats it as such),
    and every fixture in this repo is a single, self-contained dataset. Named
    rather than silently assumed."""
    for row_id in open_break_row_ids:
        existing = conn.execute(
            "SELECT first_run_id, first_seen_at FROM break_history WHERE row_id = ?",
            (row_id,)).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO break_history (row_id, reason, first_run_id, "
                "first_seen_at, last_run_id, closed_at, close_run_id) "
                "VALUES (?, '', ?, ?, ?, NULL, NULL)",
                (row_id, run_id, started_at, run_id))
        else:
            conn.execute(
                "UPDATE break_history SET last_run_id = ?, closed_at = NULL, "
                "close_run_id = NULL WHERE row_id = ?", (run_id, row_id))

    previously_open = conn.execute(
        "SELECT row_id FROM break_history WHERE closed_at IS NULL").fetchall()
    for (row_id,) in previously_open:
        if row_id in open_break_row_ids:
            continue
        if row_id not in all_row_ids:
            continue  # not part of this run's dataset at all -- not our call to close
        conn.execute(
            "UPDATE break_history SET closed_at = ?, close_run_id = ? "
            "WHERE row_id = ?", (started_at, run_id, row_id))
