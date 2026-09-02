"""Re-render `corpus/GST_HOLDOUT_RESULTS.md` from the SAVED results JSON.

    python3 corpus/render_gst_holdout.py

§65 did this once, ad hoc, and §66 needs it again. Committing it makes the
operation repeatable and auditable instead of a thing that happened in a
session, which is the whole point of the held-out protocol.

## What this does NOT do, and why that is the entire value

It never calls `score_one()`, `resolve()`, or `corpus.oracle.score()`. The
held-out GST dataset was scored **exactly once**, under §64, and every
`TP`/`FP`/`FN`/precision/recall/oracle number in
`corpus/gst_holdout_results.json` is that one run's output. Re-scoring it to
fix a report -- even a report that is genuinely wrong -- would quietly
invalidate the "run exactly once" claim, and §58 makes that risk concrete
rather than theoretical: the resolver's CP-SAT enumeration is not
reproducible run-to-run on a truncating pool, so a second run could return a
different number and no one would know which was §64's.

## The one thing it recomputes, and why that is permitted

§66 added two functions -- `absent_gap_decomposition()` and
`zero_tax_month_coverage()` -- whose outputs the new report section needs and
which did not exist when §64 wrote the JSON. They are backfilled here.

Both are PURE functions of `gstr2b.csv`/`recon_combined.json` and
`ground_truth.json` as they already sit on disk. Neither runs the resolver,
neither reads a resolver output, neither touches `corpus/oracle.py`, and
neither can change any scored figure -- they add descriptive columns
explaining a delta that was already published. Backfilling them is arithmetic
over committed data, not a re-measurement.

Every previously published number in the regenerated report is therefore
bit-for-bit §64's. The diff is: the false causal paragraph is replaced, and
two explanatory tables appear.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.score_gst import (                                       # noqa: E402
    absent_gap_decomposition, render, run_filters, zero_tax_month_coverage,
)

RESULTS = ROOT / "corpus" / "gst_holdout_results.json"
OUT = ROOT / "corpus" / "GST_HOLDOUT_RESULTS.md"
HOLDOUT_FAMILY = ROOT / "corpus" / "datasets_gst_holdout"


def backfill(result: dict) -> dict:
    """Add §66's two descriptive keys if the saved JSON predates them.

    Keyed off the dataset name already in the file, so this cannot be pointed
    at a different dataset by accident.
    """
    if "absent_gap_decomposition" in result:
        return result
    directory = ROOT / "corpus" / result["dataset"]
    if not directory.exists():
        raise SystemExit(f"{directory} does not exist; cannot backfill "
                         f"{result['dataset']}")
    truth = json.loads((directory / "ground_truth.json").read_text())
    dataset, _findings, _exceptions = run_filters(directory)
    result["absent_gap_decomposition"] = absent_gap_decomposition(dataset, truth)
    result["zero_tax_month_coverage"] = zero_tax_month_coverage(dataset)
    return result


def main() -> int:
    if not RESULTS.exists():
        print(f"{RESULTS} not found -- nothing to render", file=sys.stderr)
        return 1
    results = json.loads(RESULTS.read_text())
    scored_before = json.dumps(
        [{k: v for k, v in r.items()
          if k not in ("absent_gap_decomposition", "zero_tax_month_coverage")}
         for r in results], sort_keys=True)

    results = [backfill(r) for r in results]

    scored_after = json.dumps(
        [{k: v for k, v in r.items()
          if k not in ("absent_gap_decomposition", "zero_tax_month_coverage")}
         for r in results], sort_keys=True)
    # The backfill is additive by construction; assert it, because "I only
    # added keys" is exactly the kind of claim this repository checks.
    if scored_before != scored_after:
        print("REFUSING TO WRITE: backfill altered a scored field.",
              file=sys.stderr)
        return 1

    text = render(results)
    OUT.write_text(text + "\n")
    RESULTS.write_text(json.dumps(results, indent=1) + "\n")
    print(f"rendered {OUT} from {RESULTS} -- no dataset re-scored")
    for r in results:
        print(f"  {r['dataset']}: oracle_passed={r['oracle_passed']} "
              f"itc_risk_flag={r.get('oracle_itc_risk_flag')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
