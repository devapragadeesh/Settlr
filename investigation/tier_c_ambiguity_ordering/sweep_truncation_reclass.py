"""Which `(dataset, bank_index)` pairs are currently `Unresolved
(ENUMERATION_TRUNCATED)` from `_tier_c` with `closures.count > 1`?

    python3 investigation/tier_c_ambiguity_ordering/sweep_truncation_reclass.py

These, and only these, are predicted to flip to `Ambiguous` under §92's fix.
Run BEFORE the fix, against the current (unfixed) code, so the prediction's
claim 1 is a fresh, dated measurement rather than a reuse of
`investigation/D15_MEASUREMENT.md`'s table -- that table predates §68's
determinism fix and reusing it uncritically would repeat exactly the
"measurement taken with a broken instrument" mistake §68's own claim 1 caught
itself making.

Only `_tier_c` truncations matter here. `_verify`'s (tier A/B) enumeration
feeds only `rival_closure_count`/`rival_count_is_lower_bound` and never
reaches the `Unresolved`/`Ambiguous` branch this fix reorders at all.

Wraps `_tier_c` directly (not `closing_subsets`) so `line.index` is available
at the call site -- an exact per-line record, not a call-order correlation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import resolver.resolve as R                                         # noqa: E402
from resolver.loaders import load                                    # noqa: E402

FAMILIES = ("datasets", "datasets_v2", "datasets_gst",
            "datasets_gst_holdout", "datasets_bankside")
HERE = Path(__file__).resolve().parent

_original_tier_c = R._tier_c
_current: list[dict] = []


def _wrapped_tier_c(line, dataset, state, cap, time_budget):
    outcome = _original_tier_c(line, dataset, state, cap, time_budget)
    _current.append({"bank_index": line.index,
                     "outcome_type": type(outcome).__name__})
    return outcome


R._tier_c = _wrapped_tier_c

# `_credit_line`'s dispatcher calls the bare name `_tier_c`, resolved from
# module globals at call time, not a reference captured at definition time --
# confirmed by reading it -- so patching the module attribute after import is
# sufficient.


def dataset_dirs() -> list[Path]:
    out: list[Path] = []
    for family in FAMILIES:
        directory = REPO / "corpus" / family
        if directory.exists():
            out += [d for d in sorted(directory.iterdir())
                    if (d / "recon_combined.json").exists()]
    return out


def main() -> int:
    global _current
    report = {}
    total_flips = 0
    for directory in dataset_dirs():
        name = f"{directory.parent.name}/{directory.name}"
        _current = []
        output = R.resolve(load(directory))

        truncated_ambiguous = []
        for outcome in output.line_outcomes:
            if type(outcome).__name__ != "Unresolved":
                continue
            if outcome.reason.value != "enumeration_truncated":
                continue
            partial = outcome.partial_candidates
            if partial is not None and partial.size > 1:
                truncated_ambiguous.append({
                    "bank_index": outcome.bank_index,
                    "candidate_count": partial.size,
                    "complete": partial.complete,
                })

        total_tier_c = len(_current)
        total_truncated = sum(1 for c in _current
                              if c["outcome_type"] == "Unresolved")
        if truncated_ambiguous:
            report[name] = truncated_ambiguous
            total_flips += len(truncated_ambiguous)
        print(f"{name:<48} tier_c={total_tier_c:>4} "
              f"truncated_unresolved={total_truncated:>3} "
              f"WILL_FLIP={len(truncated_ambiguous):>3}", flush=True)

    out = HERE / "predicted_reclassification.json"
    out.write_text(json.dumps(report, indent=1, sort_keys=True))
    print(f"\n{total_flips} total (dataset, bank_index) pairs predicted to "
          f"flip Unresolved(ENUMERATION_TRUNCATED) -> Ambiguous")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
