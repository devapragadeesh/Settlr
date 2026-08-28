"""Stage 3 -- constrained reconstruction and uniqueness proof.

## Why this stage exists when `settlement_id` is already in the file

`settlement_id` is Razorpay's ASSERTION about which rows formed a batch. The
bank statement is the source of truth. Stage 3 asks a question the attestation
cannot answer:

    Given everything that was available to settle on that date, is this bank
    credit explained by ONE subset of the ledger, or by more than one?

The enumerator never sees which subset the attestation names. It is handed a
target amount and a pool and returns every subset that nets to the target. So
it can -- and does -- flag batches the attestation reports as ordinary.

Ambiguity is therefore DISCOVERED, not read. Had this stage grouped rows by
`settlement_id` and stopped, every batch would look determinate, including the
ones that provably are not.

## Where the attestation IS used, and why that is not circular

Pool construction only: rows already paid out by an EARLIER bank credit are
gone, and the attestation is how the engine knows which those are. That is
information an auditor genuinely has -- last week's settlement is banked fact.
It bounds which rows are candidates; it never chooses among them. The
distinction matters and is the reason this stage can disagree with the file it
was given.

## Selection-rule agnosticism

Nothing here assumes "maximal subset under a cap". The model is a sum equality
over a candidate pool; the same code returns the same answers if the ledger had
been formed FIFO. Eligibility (T+2 working days) bounds the pool only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from ortools.sat.python import cp_model
from scipy.optimize import linear_sum_assignment

from .loaders import Dataset, is_failed, to_date
from .model import (
    Ambiguous, Decomposition, Determinate, Resolution, Unresolved,
    resolve_from_candidates,
)

#: Fields that are all one assertion -- "this row settled, in that batch".
#: Withheld from the enumerator so a reconstruction cannot read its own answer.
WITHHELD = ("settlement_id", "settled", "settled_at", "settlement_utr")

#: Maximum tying decompositions enumerated per bank credit. A batch with more
#: than this is MORE ambiguous, not less, and is reported truncated -- never as
#: a complete list. Measured: this ledger's worst case is 2, so 32 leaves ample
#: headroom while bounding the search on a pathological pool.
ENUMERATION_CAP = 32

#: Working days from capture to settlement eligibility. BLOCKING ONLY -- it
#: bounds which rows are candidates, never which candidate is chosen.
ELIGIBILITY_WORKING_DAYS = 2

#: Deterministic-time ceiling per bank credit, in CP-SAT's own units --
#: NOT wall-clock seconds. Exceeding it is reported, not silently swapped for
#: an approximate method.
#:
#: This was `max_time_in_seconds`, a WALL-CLOCK budget, until DECISIONS.md
#: sec 49. `num_workers = 1` below makes the search ORDER reproducible, but a
#: wall-clock budget still cuts that same, reproducible order off at a
#: different POINT depending on what else the machine was doing -- the exact
#: defect sec 39 fixed on the resolver side of this project, found here by
#: accident during an unrelated verification pass. Two runs of this frozen
#: module against identical frozen input produced different
#: Determinate/Ambiguous/Unresolved outcomes on 10 of 30 corpus datasets
#: before this fix. `max_deterministic_time` is measured in CP-SAT's own
#: internal step count, so identical search orders now reach identical
#: stopping points regardless of machine load.
#:
#: The numeric value (30.0) is carried over unchanged from the wall-clock
#: figure it replaces. OR-Tools does not publish a fixed conversion between
#: deterministic-time units and wall-clock seconds -- that the two happen to
#: share a number is not a claim that they represent an equivalent amount of
#: search. Verified empirically, not assumed:
#: `investigation/nondeterminism_evidence/`.
SOLVER_TIME_LIMIT_SECONDS = 30.0


def net_contribution(row: dict) -> int:
    """Signed value a row carries into a batch: credit positive, debit negative."""
    return row["credit"] - row["debit"]


def eligible_from(row: dict) -> date:
    """T+2 working days after capture. A blocking bound, not a selection rule."""
    day = to_date(row["created_at"])
    remaining = ELIGIBILITY_WORKING_DAYS
    while remaining > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day


def withhold(row: dict) -> dict:
    """A view of a row with the settlement assertion removed."""
    return {key: value for key, value in row.items() if key not in WITHHELD}


@dataclass(frozen=True, slots=True)
class ZeroNetGroup:
    """A payment and refunds that exactly cancel.

    Such a group contributes 0 to every sum, so it can be added to or removed
    from ANY decomposition without changing the total -- making every bank
    credit ambiguous for a reason that has nothing to do with settlement. That
    is an artefact of arithmetic, not a finding, so these are removed from the
    candidate pool and reported as their own exception class.

    Detected from the ledger alone: refunds totalling the payment amount, all
    raised before the payment could have settled.
    """

    payment_id: str
    refund_ids: tuple[str, ...]
    amount: int


def find_zero_net_groups(rows: list[dict]) -> list[ZeroNetGroup]:
    refunds_for: dict[str, list[dict]] = {}
    for row in rows:
        if row["type"] == "refund" and row["payment_id"]:
            refunds_for.setdefault(row["payment_id"], []).append(row)

    groups = []
    for row in rows:
        if row["type"] != "payment" or is_failed(row):
            continue
        refunds = refunds_for.get(row["entity_id"], [])
        if not refunds or sum(r["amount"] for r in refunds) != row["amount"]:
            continue
        cutoff = eligible_from(row)
        if all(to_date(r["created_at"]) <= cutoff for r in refunds):
            groups.append(ZeroNetGroup(
                payment_id=row["entity_id"],
                refund_ids=tuple(sorted(r["entity_id"] for r in refunds)),
                amount=row["amount"]))
    return sorted(groups, key=lambda g: g.payment_id)


def enumerate_decompositions(
    pool: list[dict], target: int, cap: int = ENUMERATION_CAP
) -> tuple[list[tuple[str, ...]], bool, int, float, bool]:
    """Every minimum-deferral subset of `pool` whose net contribution is `target`.

    ## The objective, and what it is not

    A refund or adjustment is APPLIED, not selected -- a merchant does not
    choose which refunds to pay back this week. But spec sec 1.4 lets a batch
    DEFER debits when the payout would otherwise go negative, so "all pending
    debits apply" is false in general (batches 0 and 11 of this ledger defer 1
    and 5 respectively).

    So the model maximises the number of pending debits APPLIED, then
    enumerates every solution achieving that optimum. Deferral is permitted
    exactly when arithmetic forces it.

    This constrains only the DEBIT side. The payment side is entirely free:
    nothing prefers larger subsets, earlier captures, or more rows. Measured on
    this ledger, leaving the debit side free as well inflates three determinate
    batches to 3, 2 and 3 candidates -- spurious ambiguity produced by
    combinations no settlement process could generate.

    Returns `(subsets, truncated, deferred_count, seconds, over_time_budget)`.
    """
    began = time.perf_counter()
    ordered = sorted(pool, key=lambda r: r["entity_id"])
    if not ordered:
        return ([] if target != 0 else [()]), False, 0, time.perf_counter() - began, False

    debit_side = [index for index, row in enumerate(ordered)
                  if row["type"] != "payment"]

    def build():
        model = cp_model.CpModel()
        variables = [model.NewBoolVar(row["entity_id"]) for row in ordered]
        model.Add(sum(net_contribution(row) * var
                      for row, var in zip(ordered, variables)) == target)
        return model, variables

    model, variables = build()
    if debit_side:
        model.Maximize(sum(variables[i] for i in debit_side))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1          # determinism
    solver.parameters.max_deterministic_time = SOLVER_TIME_LIMIT_SECONDS
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], False, 0, time.perf_counter() - began, status == cp_model.UNKNOWN
    applied = int(solver.ObjectiveValue()) if debit_side else 0

    model, variables = build()
    if debit_side:
        model.Add(sum(variables[i] for i in debit_side) == applied)

    class Collector(cp_model.CpSolverSolutionCallback):
        def __init__(self) -> None:
            super().__init__()
            self.subsets: list[tuple[str, ...]] = []

        def on_solution_callback(self) -> None:
            self.subsets.append(tuple(sorted(
                row["entity_id"] for row, var in zip(ordered, variables)
                if self.Value(var))))
            if len(self.subsets) >= cap:
                self.StopSearch()

    collector = Collector()
    enumerator = cp_model.CpSolver()
    enumerator.parameters.enumerate_all_solutions = True
    enumerator.parameters.num_workers = 1      # determinism
    enumerator.parameters.max_deterministic_time = SOLVER_TIME_LIMIT_SECONDS
    enum_status = enumerator.Solve(model, collector)

    hit_cap = len(collector.subsets) >= cap
    # `over_time_budget` used to be `seconds > SOLVER_TIME_LIMIT_SECONDS` --
    # comparing a WALL-CLOCK measurement against what is now a
    # DETERMINISTIC-TIME budget, a unit mismatch this same change would have
    # introduced if left alone. Derived from the enumerator's own status
    # instead, matching `DECISIONS.md` sec 39's precedent: `status ==
    # OPTIMAL` means the enumeration genuinely exhausted the search space;
    # any other status means it did not, and if that was not because the cap
    # was reached, it was the deterministic-time budget.
    over_time_budget = enum_status != cp_model.OPTIMAL and not hit_cap
    # `truncated` used to be `hit_cap` alone, so an enumeration that exhausted
    # its deterministic-time budget BEFORE reaching the cap was reported
    # `truncated=False` -- the same "weaker state reported as stronger"
    # pattern sec 39 fixed on the resolver side, one level deeper in this
    # same function (`DECISIONS.md` sec 50). Cap-hit and budget-exhaustion
    # are both truncation: `enum_status != OPTIMAL` covers both, because a
    # `StopSearch()` at the cap reports `FEASIBLE`, never `OPTIMAL`, just as
    # a budget-exhausted stop does.
    truncated = enum_status != cp_model.OPTIMAL

    return (sorted(collector.subsets), truncated,
            len(debit_side) - applied, time.perf_counter() - began,
            over_time_budget)


@dataclass
class BatchReconstruction:
    bank_index: int
    bank_amount: int
    bank_date: date
    pool_ids: tuple[str, ...]
    resolution: Resolution
    deferred_debits: int
    seconds: float
    over_time_budget: bool = False


@dataclass
class Stage3Result:
    reconstructions: list[BatchReconstruction] = field(default_factory=list)
    zero_net_groups: list[ZeroNetGroup] = field(default_factory=list)
    #: entity_id -> bank index, for rows a determinate reconstruction pinned
    assigned: dict[str, int] = field(default_factory=dict)
    #: rows known to be involved in a batch, but not known WHICH candidate
    contested: dict[str, int] = field(default_factory=dict)
    erp_assignments: dict[str, str] = field(default_factory=dict)
    erp_rejected: list[tuple[str, str, int]] = field(default_factory=list)
    total_seconds: float = 0.0

    def by_bank_index(self, index: int) -> BatchReconstruction | None:
        for item in self.reconstructions:
            if item.bank_index == index:
                return item
        return None

    @property
    def ambiguous_indexes(self) -> list[int]:
        return [item.bank_index for item in self.reconstructions
                if isinstance(item.resolution, Ambiguous)]


def build_pool(
    dataset: Dataset, bank_date: date, consumed: set[str], excluded: set[str]
) -> list[dict]:
    """Candidate rows for a bank credit, settlement assertion stripped.

    Blocking rules, each derivable without knowing any answer:
      - failed payments carry `fee: null` and never settle;
      - `on_hold` rows are locked funds -- the row says so;
      - a row cannot settle before it exists;
      - a payment is eligible T+2 working days after capture;
      - rows an earlier bank credit already paid out;
      - zero-net groups, which would make every credit trivially ambiguous.
    """
    pool = []
    for row in dataset.rows:
        row_id = row["entity_id"]
        if row_id in consumed or row_id in excluded:
            continue
        if is_failed(row) or row["on_hold"]:
            continue
        if to_date(row["created_at"]) > bank_date:
            continue
        if row["type"] == "payment" and eligible_from(row) > bank_date:
            continue
        pool.append(withhold(row))
    return pool


def run(
    dataset: Dataset,
    bank_to_batch: dict[int, str],
    cap: int = ENUMERATION_CAP,
) -> Stage3Result:
    result = Stage3Result()
    result.zero_net_groups = find_zero_net_groups(dataset.rows)
    excluded = {group.payment_id for group in result.zero_net_groups}
    for group in result.zero_net_groups:
        excluded.update(group.refund_ids)

    rows_by_id = {row["entity_id"]: row for row in dataset.rows}
    consumed: set[str] = set()
    started = time.perf_counter()

    for line in sorted(dataset.bank, key=lambda b: (b.value_date, b.index)):
        pool = build_pool(dataset, line.value_date, consumed, excluded)
        subsets, truncated, deferred, seconds, over_budget = (
            enumerate_decompositions(pool, line.amount, cap))
        candidates = [Decomposition.build(rows_by_id, subset) for subset in subsets]
        resolution = resolve_from_candidates(
            candidates, bank_amount=line.amount, truncated=truncated,
            method="cpsat_min_deferral_enumeration", pool_size=len(pool),
            enumeration_cap=cap)

        result.reconstructions.append(BatchReconstruction(
            bank_index=line.index, bank_amount=line.amount,
            bank_date=line.value_date,
            pool_ids=tuple(sorted(row["entity_id"] for row in pool)),
            resolution=resolution, deferred_debits=deferred, seconds=seconds,
            over_time_budget=over_budget))

        if isinstance(resolution, Determinate):
            for row_id in resolution.decomposition.row_ids:
                result.assigned[row_id] = line.index
        elif isinstance(resolution, Ambiguous):
            for row_id in resolution.certain_rows:
                result.assigned[row_id] = line.index
            for row_id in resolution.contested_rows:
                result.contested[row_id] = line.index

        # Advance the pool. Rows an earlier credit paid out are banked fact;
        # the attestation is how the engine knows which. Used for BLOCKING the
        # next batch only -- never to choose among this batch's candidates.
        settlement_id = bank_to_batch.get(line.index)
        if settlement_id:
            consumed |= {row["entity_id"] for row in dataset.rows
                         if row["settlement_id"] == settlement_id}
        elif isinstance(resolution, Determinate):
            consumed |= set(resolution.decomposition.row_ids)

    result.total_seconds = time.perf_counter() - started
    result.erp_assignments, result.erp_rejected = hungarian_erp_residual(dataset)
    return result


#: Above this cost a Hungarian assignment is refused. `linear_sum_assignment`
#: returns a COMPLETE matching whether or not the pairs make sense, so a
#: threshold is not a refinement -- it is the only thing between the optimiser
#: and a full set of false positives.
HUNGARIAN_REJECT_COST = 10_000
#: Cost added when two rows share no identifier. Deliberately larger than any
#: amount or date term can reach, so no accumulation of weak similarity can
#: ever outweigh the absence of a shared key.
NO_SHARED_IDENTIFIER_PENALTY = 1_000_000


def hungarian_erp_residual(dataset: Dataset):
    """Optimal 1:1 assignment over the ERP residual, then a hard cost gate.

    The right tool for a balanced residual, and retained even though it assigns
    nothing on this ledger: the ERP gaps are REAL gaps. Some settled payments
    genuinely have no ERP order and some ERP orders genuinely have no payment.
    The correct output is an empty assignment with every proposed pair refused,
    and reporting the refusals is how that is distinguished from never looking.
    """
    from .stage1_exact import run as stage1_run

    stage1 = stage1_run(dataset)
    unrecorded = [row for row in dataset.rows
                  if row["entity_id"] in set(stage1.rows_without_erp)]
    orphans = [order for order in dataset.erp
               if order.invoice_no in set(stage1.erp_unjoined)]
    if not unrecorded or not orphans:
        return {}, []

    costs = []
    for row in sorted(unrecorded, key=lambda r: r["entity_id"]):
        row_date = to_date(row["created_at"])
        costs.append([
            abs(order.amount - row["amount"])
            + abs((order.invoice_date - row_date).days) * 1000
            + (0 if order.order_id == row["order_id"] else NO_SHARED_IDENTIFIER_PENALTY)
            for order in sorted(orphans, key=lambda o: o.invoice_no)
        ])

    ordered_rows = sorted(unrecorded, key=lambda r: r["entity_id"])
    ordered_orphans = sorted(orphans, key=lambda o: o.invoice_no)
    row_index, col_index = linear_sum_assignment(costs)

    assignments: dict[str, str] = {}
    rejected: list[tuple[str, str, int]] = []
    for r, c in zip(row_index, col_index):
        cost = int(costs[r][c])
        left, right = ordered_rows[r]["entity_id"], ordered_orphans[c].invoice_no
        if cost <= HUNGARIAN_REJECT_COST:
            assignments[left] = right
        else:
            rejected.append((left, right, cost))
    return assignments, sorted(rejected)
