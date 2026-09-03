"""Sec 92: a truncated enumeration that already proved `count > 1` must
report `Ambiguous`, not `Unresolved`.

Non-uniqueness needs only two witnesses, proven the instant a second closing
subset is found -- it never needs completeness, unlike uniqueness. Before
sec 92, `_tier_c` checked `not closures.complete` before `closures.count >
1`, so a truncated enumeration that had already found 200 rivals was
reported as silent, unproven `Unresolved` instead of honest, evidenced
`Ambiguous`. `resolver/tests/test_gst_risk.py::
test_a_row_that_never_settled_is_not_flagged_by_its_break_mate` is this
file's nearest sibling in shape: a single-field defect, isolated on the
smallest fixture that states it.

`resolver.resolve.closing_subsets` is monkeypatched to a fixed, hand-built
`Closures` so every case below is exact and independent of whatever CP-SAT
happens to find on any given day -- the same technique
`investigation/resolver_nondeterminism/before_after.py` and `investigation/
tier_c_ambiguity_ordering/sweep_truncation_reclass.py` already use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import resolver.resolve as R
from resolver.enumerate_closures import Closures
from resolver.loaders import load
from resolver_contract.types import Ambiguous, Unresolved, UnresolvedReason

ROOT = Path(__file__).resolve().parents[2]
#: PSP-absent by construction -- no bank line ever attests, so every line
#: falls straight to `_tier_c`. bank[5] is a real tier-C line on this
#: dataset (confirmed via `investigation/tier_c_ambiguity_ordering/
#: sweep_truncation_reclass.py`'s sweep), so it is a genuine `_tier_c`
#: call site, not a synthetic stand-in.
DATASET = ROOT / "corpus" / "datasets" / "A20_Bnone_Cmax"
TARGET_LINE = 5


def _fake_closures(row_ids: list[str], count: int, complete: bool,
                   status: str) -> Closures:
    # Real row ids, not synthetic ones -- `_candidate_set`/`_composition_of`
    # look up `rows_by_id[row_id]` to build a `Composition`, which KeyErrors
    # on a made-up id. `count` distinct one-row subsets, each a different
    # real row, is the smallest fixture that satisfies that lookup.
    subsets = tuple((row_id,) for row_id in row_ids[:count])
    return Closures(subsets=subsets, complete=complete, cap=200,
                    status=status, wall_seconds=0.0, deterministic_seconds=0.0)


def _resolve_with_fixed_closures(count, complete, status):
    """`resolve()` on `DATASET` with EVERY `closing_subsets` call replaced by
    a fixed answer -- deliberately crude (it affects tier A/B calls too, not
    just tier C), which is fine here because the only outcome inspected is
    `TARGET_LINE`'s, a confirmed tier-C line."""
    dataset = load(DATASET)
    row_ids = [row["entity_id"] for row in dataset.rows]
    original = R.closing_subsets
    R.closing_subsets = (lambda *a, **k:
                         _fake_closures(row_ids, count, complete, status))
    try:
        output = R.resolve(dataset)
    finally:
        R.closing_subsets = original
    return {o.bank_index: o for o in output.line_outcomes}[TARGET_LINE]


def test_truncated_count_gt_1_reports_ambiguous_not_unresolved():
    outcome = _resolve_with_fixed_closures(3, False, "cap_reached")
    assert isinstance(outcome, Ambiguous), type(outcome).__name__
    assert outcome.candidate_set.complete is False
    assert outcome.candidate_set.size == 3


def test_truncated_count_eq_1_still_reports_unresolved():
    """Regression guard for sec 39's defect class: a truncated SINGLE find
    must never be promoted past `Unresolved`. Unchanged by sec 92."""
    outcome = _resolve_with_fixed_closures(1, False, "time_budget_exceeded")
    assert isinstance(outcome, Unresolved), type(outcome).__name__
    assert outcome.reason is UnresolvedReason.ENUMERATION_TRUNCATED
    assert outcome.partial_candidates.size == 1
    assert outcome.partial_candidates.complete is False


def test_truncated_count_eq_0_still_reports_unresolved():
    """The other truncated-and-inconclusive case: no candidate exists at
    all. `count == 0, complete == False` is still `ENUMERATION_TRUNCATED`,
    per the first branch in `_tier_c` -- unaffected by sec 92's reordering,
    which only moves the `count > 1` branch."""
    outcome = _resolve_with_fixed_closures(0, False, "time_budget_exceeded")
    assert isinstance(outcome, Unresolved), type(outcome).__name__
    assert outcome.reason is UnresolvedReason.ENUMERATION_TRUNCATED


def test_complete_count_gt_1_still_reports_ambiguous():
    """Unchanged path: complete-and-ambiguous was already `Ambiguous`
    before sec 92, and stays `Ambiguous`, now correctly labelled
    `complete=True` rather than a sample."""
    outcome = _resolve_with_fixed_closures(2, True, "optimal")
    assert isinstance(outcome, Ambiguous), type(outcome).__name__
    assert outcome.candidate_set.complete is True
    assert outcome.candidate_set.size == 2
