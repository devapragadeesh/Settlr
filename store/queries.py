"""The read side -- and the actual payoff of Track C:
`investigation/CONTROLS_MAPPING.md` Sec.3(b) names *"no log of an outcome
changing from `Ambiguous` to `Verified` as new evidence arrived"* as an
absent control. `row_history` below is that log, reconstructed from what
`store/writer.py` persisted across runs -- not a new field bolted onto
`resolver_contract.types`, but a real answer to a question this repo's own
audit said had none.
"""

from __future__ import annotations

import json
import sqlite3

from resolver_contract.types import (AGE_BUCKETS, BREAK_ROUTING, BreakReason,
                                      ResolverOutput, age_bucket)
from store.codec import outcome_from_jsonable


def get_run(conn: sqlite3.Connection, run_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def runs_for_dataset(conn: sqlite3.Connection, dataset: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM runs WHERE dataset = ? ORDER BY started_at",
        (dataset,)).fetchall()
    return [dict(r) for r in rows]


def line_outcome(conn: sqlite3.Connection, run_id: str, bank_index: int):
    row = conn.execute(
        "SELECT outcome_json FROM line_outcomes WHERE run_id = ? AND bank_index = ?",
        (run_id, bank_index)).fetchone()
    if row is None:
        return None
    return outcome_from_jsonable(json.loads(row["outcome_json"]))


def row_outcome(conn: sqlite3.Connection, run_id: str, row_id: str):
    row = conn.execute(
        "SELECT outcome_json FROM row_outcomes WHERE run_id = ? AND row_id = ?",
        (run_id, row_id)).fetchone()
    if row is None:
        return None
    return outcome_from_jsonable(json.loads(row["outcome_json"]))


def read_resolver_output(conn: sqlite3.Connection, run_id: str) -> ResolverOutput:
    run = get_run(conn, run_id)
    if run is None:
        raise KeyError(run_id)

    line_rows = conn.execute(
        "SELECT bank_index, outcome_json FROM line_outcomes WHERE run_id = ? "
        "ORDER BY bank_index", (run_id,)).fetchall()
    line_outcomes = tuple(
        outcome_from_jsonable(json.loads(r["outcome_json"])) for r in line_rows)

    row_rows = conn.execute(
        "SELECT row_id, outcome_json FROM row_outcomes WHERE run_id = ? "
        "ORDER BY rowid", (run_id,)).fetchall()
    seen_row_json: dict[str, str] = {}
    unmatched = []
    for r in row_rows:
        # Multiple row_outcomes rows can share one outcome_json (one row per
        # row_id in a multi-row-id outcome) -- de-duplicate on the JSON text
        # itself so the reconstructed ResolverOutput.unmatched carries one
        # outcome object per original outcome, not one per row_id.
        if r["outcome_json"] in seen_row_json:
            continue
        seen_row_json[r["outcome_json"]] = r["row_id"]
        unmatched.append(outcome_from_jsonable(json.loads(r["outcome_json"])))

    return ResolverOutput(resolver=run["resolver"], dataset=run["dataset"],
                           line_outcomes=line_outcomes, unmatched=tuple(unmatched))


def open_breaks(conn: sqlite3.Connection, run_id: str) -> dict[str, list[dict]]:
    """Open breaks for one run, bucketed by `resolver_contract.types.AGE_BUCKETS`
    -- the same buckets `resolver/breaks.py` itself uses, so this is a live
    view over the same aging model, not a parallel one."""
    rows = conn.execute(
        "SELECT row_id, reason, age_days, first_seen FROM row_outcomes "
        "WHERE run_id = ? AND disposition = 'OpenBreak' ORDER BY age_days DESC",
        (run_id,)).fetchall()
    buckets: dict[str, list[dict]] = {name: [] for name, _, _ in AGE_BUCKETS}
    for row in rows:
        bucket = age_bucket(row["age_days"])
        buckets[bucket].append(dict(row))
    return buckets


def owner_for_reason(reason: str) -> tuple[str, str]:
    """`(owner, close_condition)` for a `row_outcomes.reason` string, per
    `resolver_contract.types.BREAK_ROUTING` -- the one place `agents/` may
    learn a break's routing without importing `resolver_contract` itself
    (`tests/test_agent_isolation.py` enforces that boundary)."""
    return BREAK_ROUTING[BreakReason(reason)]


def break_lifecycle(conn: sqlite3.Connection, row_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM break_history WHERE row_id = ?", (row_id,)).fetchone()
    return dict(row) if row else None


def _assigned_rows(conn: sqlite3.Connection, run_id: str) -> dict[str, str]:
    """`row_id -> the outcome kind that assigned it` for one run, derived
    from `Verified`/`Reconstructed` compositions rather than stored as a
    separate column -- `ResolverOutput.row_assignments` on the live object is
    itself derived the same way (its own docstring: "DERIVED from the
    outcomes rather than reported alongside them"), so this mirrors the
    contract's own design rather than inventing a second notion of
    assignment.
    """
    rows = conn.execute(
        "SELECT kind, outcome_json FROM line_outcomes WHERE run_id = ? "
        "AND kind IN ('Verified', 'Reconstructed')", (run_id,)).fetchall()
    assigned: dict[str, str] = {}
    for row in rows:
        payload = json.loads(row["outcome_json"])
        composition = payload["composition"]
        for row_id in composition["credit_ids"] + composition["debit_ids"]:
            assigned[row_id] = row["kind"]
    return assigned


def row_history(conn: sqlite3.Connection, dataset: str, row_id: str) -> list[dict]:
    """For every run of `dataset`, in order: was this row assigned (and by
    which outcome kind), or unmatched (and as what disposition/reason)? This
    is the reconstruction of "did this row's outcome change over time, and
    what changed it" that `investigation/CONTROLS_MAPPING.md` Sec.3(b) names
    as absent from the repo before Track C.
    """
    history: list[dict] = []
    for run in runs_for_dataset(conn, dataset):
        run_id = run["run_id"]
        assigned = _assigned_rows(conn, run_id)
        if row_id in assigned:
            history.append(dict(run_id=run_id, started_at=run["started_at"],
                                 state=assigned[row_id], reason=None))
            continue
        row = conn.execute(
            "SELECT disposition, reason FROM row_outcomes WHERE run_id = ? "
            "AND row_id = ?", (run_id, row_id)).fetchone()
        if row is not None:
            history.append(dict(run_id=run_id, started_at=run["started_at"],
                                 state=row["disposition"], reason=row["reason"]))
    return history
