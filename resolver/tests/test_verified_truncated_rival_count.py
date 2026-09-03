"""Sec 93: `OutcomeAccounting` must count `Verified` outcomes whose rival
closure count is a floor, not just truncated `Ambiguous` outcomes.

`DECISIONS.md` sec 77 measured that `incomplete_enumerations` reads 0 at
every resolver-at-scale size even though every `Verified` above ~5,000 rows
carries `rival_count_is_lower_bound=True` -- because that counter is only
incremented for `Ambiguous`. Named there as a gap, not fixed there because a
`resolver_contract` change needs its own dated decision. This is that
decision's test: it forces the same truncation cheaply, with `cap=1` on a
small dataset, rather than needing the ~26-minute scale sweep to observe it.
"""

from __future__ import annotations

from pathlib import Path

from resolver.loaders import load
from resolver.resolve import resolve
from resolver_contract.types import Verified

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"


def test_a_starved_cap_produces_a_lower_bounded_verified_and_is_counted():
    output = resolve(load(DATASET), cap=1, time_budget=3.0)
    truncated_verified = [o for o in output.line_outcomes
                          if isinstance(o, Verified)
                          and o.rival_count_is_lower_bound]
    assert truncated_verified, (
        "fixture assumption failed: cap=1 produced no truncated Verified on "
        f"{DATASET.name} -- pick a dataset/cap where at least one Verified "
        "line's pool has more than one row")

    accounting = output.accounting()
    assert (accounting.verified_with_truncated_rival_count
            == len(truncated_verified))


def test_a_generous_cap_counts_zero():
    """Regression guard: the new counter must not fire when nothing
    truncated -- otherwise it would just be `verified` restated."""
    output = resolve(load(DATASET), cap=200, time_budget=5.0)
    accounting = output.accounting()
    truncated_verified = [o for o in output.line_outcomes
                          if isinstance(o, Verified)
                          and o.rival_count_is_lower_bound]
    assert accounting.verified_with_truncated_rival_count == len(truncated_verified)
