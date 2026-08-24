"""The closure register: every subset that closes, under NO objective.

## Why this is the highest-value thing in `corpus/`

The frozen ground-truth key records `tying_decompositions` -- the subsets that
tie **at the maximum feasible sum**. `investigation/DEFECT_REPORT.md` §2
measured what that actually means: two primary bank credits had **three
closing subsets each** and were recorded, and reported, as determinate. The
rivals were never constructed, so they could never surface as a tie, and no
truncation flag was raised because nothing was truncated.

A register built with an objective can only ever confirm the objective. This
one carries **no objective at all** -- the model is `sum(net_i · x_i) == target`
and nothing else -- which is what makes D1 *measurable* rather than latent.

## Two different facts, deliberately separated

The frozen key conflates them; the corpus key does not.

| field | what it is | known at pool 60? |
|---|---|---|
| `composition` | the subset the generator actually selected. A fact about the **generative process**. | yes, exactly, O(1) |
| `closure` | every subset of the pool closing to the observed payout. A fact about the **reconstruction problem**. | no -- capped, and it says so |

A solver that returns a confident answer where `closure.count > 1` is wrong
**even when it matches `composition`**, because it cannot have known. That is
`SETTLEMENT_SPEC.md` §2's ambiguity contract, generalised and made scoreable.

## `recoverable` is three-valued, and `unknown` is first-class

    unique      exactly one closing subset, enumeration COMPLETE
    not_unique  two or more found (a lower bound is still a proof of >1)
    unknown     enumeration hit the cap or the time budget with one found

The eval harness must be able to say *"we prove non-uniqueness in 34 of 40; in
6 we could not decide within budget, excluded from the statistic and reported
separately."* That is defensible. "We enumerated 500 and called it ambiguous"
is not, because 500-of-many and 2-of-2 are both "ambiguous" and are not the
same claim.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Sequence

from ortools.sat.python import cp_model

__all__ = ["ClosureRegister", "enumerate_closing_subsets"]

#: Far above any resolver's cap. `matching/stage3_solver.py` uses 32; a
#: register that stopped anywhere near that could not tell a resolver's
#: truncation from the truth.
DEFAULT_CAP = 500
#: Per-batch wall-clock ceiling. At pool 60 the register is `cap_reached`
#: regardless -- non-uniqueness is already PROVEN at count >= 2 -- and capped
#: instances are excluded from the premise-sharing statistic and reported as
#: excluded, so a tighter budget costs nothing analytically and keeps
#: generation terminating. Exceeding it is recorded as `time_budget_exceeded`,
#: never as a complete enumeration.
DEFAULT_TIME_BUDGET = 15.0


@dataclass(frozen=True, slots=True)
class ClosureRegister:
    """Every closing subset of a pool, or an explicit, labelled sample."""

    #: Sorted tuples of row ids. A SAMPLE when `complete` is False.
    subsets: tuple[tuple[str, ...], ...]
    count: int
    cap: int
    complete: bool
    status: str
    wall_seconds: float
    #: How the subsets were produced. Recorded because CP-SAT's enumeration
    #: order is NOT uniform, and a sample that is not uniform must never be
    #: reported as if it were.
    sampling: str = "cpsat_enumeration_order (NOT uniform)"

    @property
    def lower_bound(self) -> int:
        """A proof that at least this many closing subsets exist."""
        return self.count

    @property
    def recoverable(self) -> str:
        if self.count >= 2:
            return "not_unique"          # a lower bound of 2 already proves it
        if self.count == 1 and self.complete:
            return "unique"
        if self.count == 0 and self.complete:
            return "no_closure"
        return "unknown"

    @property
    def is_determined(self) -> bool:
        """The `DeterminedInstance` precondition from the resolver contract."""
        return self.recoverable == "unique"

    def contains(self, row_ids: Sequence[str]) -> bool:
        return tuple(sorted(row_ids)) in set(self.subsets)

    def to_json(self, sample_limit: int = 64) -> dict:
        """The ground-truth shape. The subset list is capped for file size and
        says so -- `count` is the number found, `len(subsets)` may be less."""
        return {
            "count": self.count,
            "cap": self.cap,
            "complete": self.complete,
            "lower_bound": self.lower_bound,
            "recoverable": self.recoverable,
            "status": self.status,
            "sampling": self.sampling,
            "wall_seconds": round(self.wall_seconds, 3),
            "subsets": [list(s) for s in self.subsets[:sample_limit]],
            "subsets_are_a_sample": len(self.subsets) > sample_limit
                                    or not self.complete,
        }


def enumerate_closing_subsets(
    pool: Sequence[tuple[str, int]],
    target: int,
    *,
    cap: int = DEFAULT_CAP,
    time_budget: float = DEFAULT_TIME_BUDGET,
    seed: int = 0,
) -> ClosureRegister:
    """Every subset of `pool` whose signed contributions sum to `target`.

    `pool` is `(row_id, net_contribution)` with credits positive and debits
    negative -- the same signed convention the solver's pool uses, so the two
    are asking exactly the same question and any difference in answer is a
    difference in method rather than in framing.

    **There is no objective.** No maximisation, no minimisation, no
    tie-breaking, no preference for applying debits. That absence is the whole
    point of the module.

    Determinism: one worker and a fixed seed. CP-SAT's enumeration order is
    nondeterministic across workers, and "deterministic across runs" failing on
    exactly the new component would be an unforced error.
    """
    began = time.perf_counter()
    ordered = sorted(pool, key=lambda item: item[0])
    if not ordered:
        empty_closes = target == 0
        return ClosureRegister(
            subsets=((),) if empty_closes else (),
            count=1 if empty_closes else 0, cap=cap, complete=True,
            status="empty_pool", wall_seconds=time.perf_counter() - began,
            sampling="exhaustive")

    model = cp_model.CpModel()
    variables = [model.NewBoolVar(row_id) for row_id, _value in ordered]
    model.Add(sum(value * var for (_row_id, value), var
                  in zip(ordered, variables)) == target)

    class Collector(cp_model.CpSolverSolutionCallback):
        def __init__(self) -> None:
            super().__init__()
            self.subsets: list[tuple[str, ...]] = []

        def on_solution_callback(self) -> None:
            self.subsets.append(tuple(sorted(
                row_id for (row_id, _value), var in zip(ordered, variables)
                if self.Value(var))))
            if len(self.subsets) >= cap:
                self.StopSearch()

    collector = Collector()
    solver = cp_model.CpSolver()
    solver.parameters.enumerate_all_solutions = True
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = seed
    solver.parameters.max_time_in_seconds = time_budget
    status = solver.Solve(model, collector)

    elapsed = time.perf_counter() - began
    hit_cap = len(collector.subsets) >= cap
    timed_out = status == cp_model.UNKNOWN or (
        elapsed >= time_budget and status != cp_model.OPTIMAL)
    complete = not hit_cap and not timed_out

    if hit_cap:
        label = "cap_reached"
    elif timed_out:
        label = "time_budget_exceeded"
    else:
        label = solver.StatusName(status).lower()

    return ClosureRegister(
        subsets=tuple(sorted(collector.subsets)),
        count=len(collector.subsets), cap=cap, complete=complete,
        status=label, wall_seconds=elapsed)


def cross_line_exclusive(
    register: ClosureRegister, subset: Sequence[str],
    other_targets: Sequence[int], pool: Sequence[tuple[str, int]],
) -> bool:
    """Does `subset` close any OTHER credit in the window as well?

    The corpus records this so `Reconstructed`'s `CROSS_LINE_EXCLUSIVITY`
    requirement is scoreable rather than merely stated. At the three bank
    lines that produced the 50 wrong rows, per-credit closure was unique and
    the answer was still wrong -- because the subset was the true composition
    of a *later* credit. That is the property this function measures.
    """
    values = dict(pool)
    total = sum(values.get(row_id, 0) for row_id in subset)
    return total not in set(other_targets)
