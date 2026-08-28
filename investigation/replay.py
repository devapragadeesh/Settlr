"""Shared investigation harness. DIAGNOSIS ONLY -- imports matching/, never edits it.

The enumerator here is INDEPENDENT of `matching.stage3_solver`. That is
deliberate: auditing the engine with the engine's own enumeration would not be
able to see a defect that lives in the enumeration.

Two differences from the engine's enumerator, and both matter:

  1. **No objective.** `stage3_solver.enumerate_decompositions` first maximises
     the number of applied debits, then enumerates ONLY solutions achieving
     that optimum. Any closing subset that applies fewer debits is never seen
     and therefore can never be reported as a tie. This module enumerates every
     closing subset regardless.
  2. **A much larger cap.** The engine stops at `ENUMERATION_CAP = 32`. This
     module goes to `HARD_CAP` and reports truncation explicitly, so "the
     engine saw one" can be distinguished from "there was one".
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ortools.sat.python import cp_model  # noqa: E402

from matching.loaders import Dataset, is_failed, load, to_date  # noqa: E402
from matching.model import Ambiguous, Determinate, Unresolved  # noqa: E402
from matching.stage3_solver import (  # noqa: E402
    ENUMERATION_CAP, SOLVER_TIME_LIMIT_SECONDS, build_pool, eligible_from,
    find_zero_net_groups, net_contribution, withhold)

#: how many closing subsets to enumerate before giving up. Far above the
#: engine's 32 so that "more than the engine could see" is measurable.
HARD_CAP = 500
HARD_TIME_LIMIT = 20.0


def all_closing_subsets(pool, target, cap=HARD_CAP, time_limit=HARD_TIME_LIMIT):
    """EVERY subset of `pool` whose net contribution equals `target`.

    No objective, no deferral preference, no tie-breaking. Just closure.
    Returns (subsets, truncated, seconds, status).
    """
    import time as _time
    began = _time.perf_counter()
    ordered = sorted(pool, key=lambda r: r["entity_id"])
    if not ordered:
        return ([] if target != 0 else [()]), False, 0.0, "EMPTY_POOL"

    model = cp_model.CpModel()
    variables = [model.NewBoolVar(row["entity_id"]) for row in ordered]
    model.Add(sum(net_contribution(row) * var
                  for row, var in zip(ordered, variables)) == target)

    class Collector(cp_model.CpSolverSolutionCallback):
        def __init__(self):
            super().__init__()
            self.subsets = []

        def on_solution_callback(self):
            self.subsets.append(tuple(sorted(
                row["entity_id"] for row, var in zip(ordered, variables)
                if self.Value(var))))
            if len(self.subsets) >= cap:
                self.StopSearch()

    collector = Collector()
    solver = cp_model.CpSolver()
    solver.parameters.enumerate_all_solutions = True
    solver.parameters.num_workers = 1
    solver.parameters.max_time_in_seconds = time_limit
    status = solver.Solve(model, collector)
    elapsed = _time.perf_counter() - began
    truncated = (len(collector.subsets) >= cap
                 or solver.StatusName(status) in ("UNKNOWN", "FEASIBLE"))
    return sorted(collector.subsets), truncated, elapsed, solver.StatusName(status)


@dataclass
class LineTrace:
    """One bank line, as the engine saw it and as the data actually is."""
    bank_index: int
    utr: str
    amount: int
    value_date: date
    attested_settlement: str | None      # what stage1/2 joined it to, if anything
    pool_ids: tuple                       # the pool the ENGINE used (post-consumption)
    engine_kind: str
    engine_rows: tuple = ()               # rows the engine assigned to this line
    engine_candidates: int = 0
    # independent enumeration over the ENGINE's pool
    closing_subsets: list = field(default_factory=list)
    closing_truncated: bool = False
    closing_status: str = ""
    # independent enumeration over the UNCONSUMED eligible pool
    free_pool_size: int = 0
    free_closing_count: int = 0
    free_truncated: bool = False
    consumed_rows: tuple = ()             # rows this line removed from later pools
    consumption_reason: str = ""


def replay(dataset: Dataset, bank_to_batch: dict, truth: dict,
           free_pool: bool = True) -> list[LineTrace]:
    """Re-run stage 3's loop, recording what the engine could NOT see.

    Mirrors `stage3_solver.run` exactly in pool construction and consumption so
    the trace describes the real execution, then adds the independent
    enumeration alongside.
    """
    from matching.stage3_solver import enumerate_decompositions
    from matching.model import resolve_from_candidates
    from matching.model import Decomposition

    zero_net = find_zero_net_groups(dataset.rows)
    excluded = {g.payment_id for g in zero_net}
    for group in zero_net:
        excluded.update(group.refund_ids)

    rows_by_id = {row["entity_id"]: row for row in dataset.rows}
    consumed: set[str] = set()
    traces: list[LineTrace] = []

    for line in sorted(dataset.bank, key=lambda b: (b.value_date, b.index)):
        pool = build_pool(dataset, line.value_date, consumed, excluded)
        subsets, truncated, deferred, _, _ = enumerate_decompositions(
            pool, line.amount, ENUMERATION_CAP)
        candidates = [Decomposition.build(rows_by_id, s) for s in subsets]
        resolution = resolve_from_candidates(
            candidates, bank_amount=line.amount, truncated=truncated,
            method="replay", pool_size=len(pool), enumeration_cap=ENUMERATION_CAP)

        closing, closing_trunc, _, status = all_closing_subsets(pool, line.amount)

        if free_pool:
            unconsumed = build_pool(dataset, line.value_date, set(), excluded)
            free_closing, free_trunc, _, _ = all_closing_subsets(
                unconsumed, line.amount)
        else:
            unconsumed, free_closing, free_trunc = [], [], False

        trace = LineTrace(
            bank_index=line.index, utr=line.utr, amount=line.amount,
            value_date=line.value_date,
            attested_settlement=bank_to_batch.get(line.index),
            pool_ids=tuple(sorted(r["entity_id"] for r in pool)),
            engine_kind=type(resolution).__name__,
            engine_candidates=len(getattr(resolution, "candidates", ()) or
                                  ([1] if isinstance(resolution, Determinate) else [])),
            closing_subsets=closing, closing_truncated=closing_trunc,
            closing_status=status,
            free_pool_size=len(unconsumed), free_closing_count=len(free_closing),
            free_truncated=free_trunc,
        )

        if isinstance(resolution, Determinate):
            trace.engine_rows = resolution.decomposition.row_ids
        elif isinstance(resolution, Ambiguous):
            trace.engine_rows = tuple(sorted(resolution.certain_rows))

        # --- consumption, mirroring stage3_solver.run exactly ---
        settlement_id = bank_to_batch.get(line.index)
        if settlement_id:
            newly = {r["entity_id"] for r in dataset.rows
                     if r["settlement_id"] == settlement_id}
            trace.consumption_reason = "attestation"
        elif isinstance(resolution, Determinate):
            newly = set(resolution.decomposition.row_ids)
            trace.consumption_reason = "UNCORROBORATED_DETERMINATE"
        else:
            newly = set()
            trace.consumption_reason = "none"
        trace.consumed_rows = tuple(sorted(newly - consumed))
        consumed |= newly
        traces.append(trace)

    return traces


def load_pair(which: str):
    """(dataset, truth, bank_to_batch) for 'primary' or 'holdout'."""
    import json
    from matching import run as run_cascade
    if which == "primary":
        dataset = load()
        truth = json.loads(
            (ROOT / "engine/ground_truth/ground_truth.json").read_text())
    else:
        dataset = load(ROOT / "holdout/data")
        truth = json.loads(
            (ROOT / "holdout/ground_truth/ground_truth.json").read_text())
    result = run_cascade(dataset=dataset)
    return dataset, truth, result


def true_batch_of(truth: dict) -> dict:
    out = {}
    for batch in truth["batches"]:
        for row_id in batch["credit_ids"] + batch["debit_ids"]:
            out[row_id] = batch["settlement_id"]
    return out
