"""Does sec 92's fix change ANY outcome on the held-out GST dataset?

    python3 investigation/tier_c_ambiguity_ordering/holdout_reach_check.py

**Corrected after a first draft got this wrong.** The first version of this
script tested "does ANY `_tier_c` enumeration truncate on this dataset,"
reasoning from `investigation/resolver_nondeterminism/outcomes_after.json`
that the answer was zero. That reasoning was WRONG: the dataset has 4
`_tier_c` truncations (bank[20,23,30,41]), not zero. But the fix's actual
question is narrower than "does truncation happen" -- it is "does a
TRUNCATED enumeration with `count > 1` happen", since only that branch is
reordered. Checked directly (`investigation/tier_c_ambiguity_ordering/
outcomes_before.json`/`outcomes_after.json`): all 4 truncated lines have
`partial_candidates is None`, which only happens in `_tier_c`'s FIRST branch
(`closures.count == 0`) -- untouched by sec 92's reordering, which only moves
the `count > 1` branch. So the bottom-line conclusion (no outcome changes on
this dataset) was right; the stated REASON was wrong, and is corrected here
rather than left standing. See `PREDICTION.md`'s own correction.

Never opens `corpus/GST_HOLDOUT_RESULTS.md` or `corpus/gst_holdout_results.json`
in write mode -- checkable directly: neither path appears anywhere in this
file except this sentence.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import resolver.resolve as R                                         # noqa: E402
from resolver.loaders import load                                    # noqa: E402

TARGET = (REPO / "corpus" / "datasets_gst_holdout"
         / "A20_B100_Cmax_gst_holdout")

_original_tier_c = R._tier_c
_current: list[dict] = []


def _wrapped_tier_c(line, dataset, state, cap, time_budget):
    outcome = _original_tier_c(line, dataset, state, cap, time_budget)
    _current.append({"bank_index": line.index,
                     "outcome_type": type(outcome).__name__})
    return outcome


R._tier_c = _wrapped_tier_c


def main() -> int:
    output = R.resolve(load(TARGET))
    truncated_enum = []
    reclassifying = []
    for outcome in output.line_outcomes:
        if not (type(outcome).__name__ == "Unresolved"
                and outcome.reason.value == "enumeration_truncated"):
            continue
        truncated_enum.append(outcome.bank_index)
        partial = outcome.partial_candidates
        if partial is not None and partial.size > 1:
            reclassifying.append((outcome.bank_index, partial.size))

    print(f"_tier_c calls: {len(_current)}")
    print(f"ENUMERATION_TRUNCATED outcomes: {len(truncated_enum)} "
          f"{truncated_enum}")
    print(f"of those, with count > 1 (sec92's actual reordering target): "
          f"{len(reclassifying)} {reclassifying}")

    reached = len(reclassifying) > 0
    print(f"\nsec92's fix changes an outcome on this dataset: {reached}")
    if reached:
        print("UNEXPECTED -- the prediction, corrected, said zero. "
              "Investigate before trusting the 'held-out untouched' claim.")
        return 1
    print("Confirmed: zero truncated enumerations with count > 1, so "
          "sec92's reordering changes nothing here -- even though "
          f"{len(truncated_enum)} lines DO truncate, none qualify for "
          "reclassification. corpus/GST_HOLDOUT_RESULTS.md and "
          "gst_holdout_results.json were never opened by this script and "
          "need no verification beyond the SHA-256 check run alongside it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
