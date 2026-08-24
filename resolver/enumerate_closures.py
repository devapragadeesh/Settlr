"""Every subset of a pool that closes to a target. NO OBJECTIVE.

Contract 2.1: an objective may only RANK an already-complete candidate set,
never filter one before uniqueness is tested. This module therefore has no
objective at all -- the model is `sum(net_i * x_i) == target` and nothing else.

That absence is the whole point. The previous engine maximised applied debits
and then enumerated only the solutions achieving that optimum, so rival closing
subsets were never constructed, could never surface as a tie, and **no
truncation flag was raised because nothing was truncated**. Two bank credits
had three closing subsets each and were reported `Determinate`.

This is a SEPARATE implementation from `corpus/generator/closure.py` on
purpose. The corpus's register is the independent yardstick the oracle scores
against; if the resolver called into it, "the resolver's k agrees with the
corpus's k" would be a tautology rather than a measurement (contract 6.2).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

from ortools.sat.python import cp_model

#: Far below the corpus register's 500. A resolver that enumerated as deeply as
#: the yardstick could never be caught truncating, and truncation is the
#: abstention loophole contract 4.5 names.
DEFAULT_CAP = 200
DEFAULT_TIME_BUDGET = 10.0


@dataclass(frozen=True, slots=True)
class Closures:
    """What the resolver actually built. `complete=False` means it stopped."""

    subsets: tuple[tuple[str, ...], ...]
    complete: bool
    cap: int
    status: str
    wall_seconds: float

    @property
    def count(self) -> int:
        return len(self.subsets)

    @property
    def is_unique(self) -> bool:
        """Exactly one, PROVEN by a complete enumeration.

        One found under truncation is not uniqueness -- it is one found. The
        distinction is the difference between `Reconstructed` and
        `Unresolved(enumeration_truncated)`.
        """
        return self.count == 1 and self.complete


def closing_subsets(pool: Sequence[tuple[str, int]], target: int, *,
                    cap: int = DEFAULT_CAP,
                    time_budget: float = DEFAULT_TIME_BUDGET,
                    seed: int = 0) -> Closures:
    began = time.perf_counter()
    ordered = sorted(pool, key=lambda item: item[0])
    if not ordered:
        closes = target == 0
        return Closures(subsets=((),) if closes else (), complete=True,
                        cap=cap, status="empty_pool",
                        wall_seconds=time.perf_counter() - began)

    model = cp_model.CpModel()
    variables = [model.NewBoolVar(row_id) for row_id, _value in ordered]
    model.Add(sum(value * var for (_row_id, value), var
                  in zip(ordered, variables)) == target)

    class Collector(cp_model.CpSolverSolutionCallback):
        def __init__(self) -> None:
            super().__init__()
            self.found: list[tuple[str, ...]] = []

        def on_solution_callback(self) -> None:
            self.found.append(tuple(sorted(
                row_id for (row_id, _value), var in zip(ordered, variables)
                if self.Value(var))))
            if len(self.found) >= cap:
                self.StopSearch()

    collector = Collector()
    solver = cp_model.CpSolver()
    solver.parameters.enumerate_all_solutions = True
    solver.parameters.num_workers = 1          # determinism across runs
    solver.parameters.random_seed = seed
    solver.parameters.max_time_in_seconds = time_budget
    status = solver.Solve(model, collector)

    elapsed = time.perf_counter() - began
    hit_cap = len(collector.found) >= cap
    timed_out = status == cp_model.UNKNOWN or (
        elapsed >= time_budget and status != cp_model.OPTIMAL)
    return Closures(
        subsets=tuple(sorted(collector.found)),
        complete=not hit_cap and not timed_out,
        cap=cap,
        status=("cap_reached" if hit_cap else
                "time_budget_exceeded" if timed_out else
                solver.StatusName(status).lower()),
        wall_seconds=elapsed)
