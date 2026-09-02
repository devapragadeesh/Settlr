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

#: CP-SAT DETERMINISTIC-time units, NOT wall-clock seconds. This was
#: `max_time_in_seconds = 10.0` until `DECISIONS.md` §67/§68 — §39's class,
#: fourth instance, and the first one inside the resolver written to prevent
#: it. A wall-clock budget makes the truncation point depend on what else the
#: machine is doing, so two runs of the same search on the same input stop at
#: different places. `num_workers = 1` fixes the search ORDER; only a
#: deterministic budget fixes where that order is cut off.
#:
#: The numeral is carried over from the old wall-clock value on §49's
#: reasoning: OR-Tools publishes no conversion between deterministic units and
#: seconds, by design — that is the whole reason the parameter exists — so
#: keeping 10.0 preserves the budget's order of magnitude WITHOUT claiming it
#: buys an equivalent amount of search. See `investigation/
#: resolver_nondeterminism/PREDICTION.md` §4 for what would revisit it.
DEFAULT_DETERMINISTIC_BUDGET = 10.0


@dataclass(frozen=True, slots=True)
class Closures:
    """What the resolver actually built. `complete=False` means it stopped."""

    subsets: tuple[tuple[str, ...], ...]
    complete: bool
    cap: int
    status: str
    #: Externally measured wall time. Kept because it is genuinely useful and
    #: genuinely wall time -- but it is NO LONGER the frame the budget is
    #: enforced in, and nothing may derive a status or a claim from it. That
    #: is exactly the mixture §39 removed from `complete` and §68 removed from
    #: `status`.
    wall_seconds: float
    #: What the solver itself spent, in the same units as the budget. This is
    #: the only quantity that may be compared against `time_budget`, and it is
    #: recorded so that "did the budget bind here?" is answerable from the
    #: output rather than by re-deriving it from a clock.
    deterministic_seconds: float = 0.0

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
                    time_budget: float = DEFAULT_DETERMINISTIC_BUDGET,
                    seed: int = 0) -> Closures:
    """`time_budget` is in CP-SAT DETERMINISTIC-time units. The parameter name
    is kept -- it is threaded through `resolve()`, `corpus/score_resolver.py`,
    `corpus/score_gst.py` and two CLIs -- but its FRAME changed in §68 and a
    caller passing "seconds" is now passing something else. See
    `DEFAULT_DETERMINISTIC_BUDGET`.
    """
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
    # sec 68. Was `max_time_in_seconds` -- a WALL-CLOCK budget, so the point at
    # which this enumeration was cut off depended on what else the machine was
    # doing. sec 49 made this exact swap in `matching/stage3_solver.py`; the
    # resolver written to prevent that defect class carried it for four
    # sections longer than the engine it replaced.
    solver.parameters.max_deterministic_time = time_budget
    status = solver.Solve(model, collector)

    elapsed = time.perf_counter() - began
    # The solver's OWN accounting, in the SAME units as `time_budget`. The
    # externally measured `elapsed` is no longer comparable to the budget at
    # all -- one is seconds, the other is deterministic units -- so the
    # comparison below could not have been left alone even if we wanted to.
    consumed = solver.deterministic_time
    hit_cap = len(collector.found) >= cap
    # FRAME (`DECISIONS.md` sec 44, instance F3), now CLOSED by sec 68.
    #
    # This line used to read `elapsed >= time_budget`, mixing an EXTERNALLY
    # measured wall clock with the solver's INTERNAL status -- the exact
    # mixture sec 39 removed from `complete` twenty lines below, which survived
    # the fix that removed it, and which sec 44 retained deliberately as
    # evidence for how this defect class hides.
    #
    # sec 68 does not tidy it away; it makes it UNSTATEABLE. Under a
    # deterministic budget the two operands are not in the same units, so the
    # frame mixture is now a type error rather than a subtle one, and the only
    # comparison that means anything is the solver's own consumption against
    # its own budget. Both operands below come from CP-SAT.
    #
    # Still LABEL-ONLY. `budget_exhausted` reaches `status` and NOTHING else.
    # It must never be allowed to reach `complete`, which is a soundness claim;
    # the moment it does, sec 39's defect is back.
    #
    # `status == UNKNOWN` alone is NOT sufficient and this was measured, not
    # assumed: a solve that stops on its budget having already found solutions
    # returns FEASIBLE, not UNKNOWN. Checking only UNKNOWN would silently
    # relabel a truncated enumeration as a clean `feasible`.
    budget_exhausted = status == cp_model.UNKNOWN or (
        consumed >= time_budget and status != cp_model.OPTIMAL)
    # `complete` means ONE thing: CP-SAT exhausted the search space and said so.
    #
    # It used to mean "we did not hit the cap and the clock we measured
    # OUTSIDE did not run out", which is a different and weaker statement. When
    # the solver stopped on its own internal budget at, say, 9.98 of an
    # externally-measured 10 unit budget, `timed_out` was False and a
    # truncated enumeration was recorded as exhaustive. Measured at
    # `corpus/datasets/A40_Bnone_Cmax` bank[7] under CPU load: 194 subsets
    # returned with `complete=True` and the truth not among them. Run alone the
    # same line correctly reports 200 / cap_reached.
    #
    # That is this repository's own defect class -- a claim of a stronger
    # epistemic state than was measured -- inside the resolver written to
    # prevent it, and it is a soundness hazard rather than a cosmetic one:
    # `Reconstructed` requires unique closure PROVEN COMPLETE, so a truncated
    # set of size one could have been promoted to a confident answer.
    # See DECISIONS.md 39.
    return Closures(
        subsets=tuple(sorted(collector.found)),
        complete=status == cp_model.OPTIMAL,
        cap=cap,
        status=("cap_reached" if hit_cap else
                "time_budget_exceeded" if budget_exhausted else
                solver.StatusName(status).lower()),
        wall_seconds=elapsed,
        deterministic_seconds=consumed)
