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

import hashlib
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

#: The seed, and the fact that it was committed before the data existed, are
#: the entire basis of this document's held-out claim. `corpus/SEEDS.txt`
#: "## 3. GST/ITC HELD-OUT".
HOLDOUT_SEED = 20261013
HOLDOUT_AXIS_POINT = "A20_B100_Cmax_gst_holdout"

#: `DECISIONS.md` §63 froze these six files by content hash BEFORE
#: `corpus/datasets_gst_holdout/` existed, and §64 ran the scoring exactly once
#: against that frozen code on 2026-08-31. The header below recomputes them and
#: reports drift rather than restating a block that can go stale -- which is
#: precisely what happened to §63's own copy.
FROZEN_AT_63 = {
    "resolver/loaders.py":
        "dec87ace1aa7f4c8accb88494842306df8cdd1b601d0e2e95f9f7303a11e9e05",
    "resolver/breaks.py":
        "bfd91818c15bfcaf2f801951bd9c0560f6f0a3ad876d9a4382d73a642e8b996b",
    "resolver/resolve.py":
        "9b72981c4399b0adddcec55a74492526180171e37fe882d77af3405386f6cbb1",
    "resolver_contract/types.py":
        "83842068b93d3fc9ad45d8b598a4778e120b32ad1610449ec7476fe0511deeaa",
    "corpus/oracle.py":
        "edfadde49c694af90bce0082b45fbbb57d4bf8384790c3ff3c68fd693b219d09",
    "corpus/score_gst.py":
        "7da59dd119581f0971ded4ff74d2c528e0242bc7c659a3a71f6bd73866bea4b5",
}


def provenance_header() -> str:
    """The two facts a held-out claim rests on: the seed, and the freeze.

    This document carried neither until 2026-09-03. Every number in it was
    produced by a single run against code frozen before the data existed, and
    a reader had no way to see that from the document itself -- they had to
    already know to go read `DECISIONS.md` §63 and §64. A held-out result that
    does not state its own provenance is asking to be taken on trust, which is
    the one thing this repository declines to ask for anywhere else.

    The hash table is RECOMPUTED at render time rather than restated. §63's
    own copy of it no longer verifies -- two of the six files legitimately
    changed after §64 -- and a frozen block that silently stops matching is
    worse than no block at all.
    """
    lines = [
        "> ## Provenance",
        ">",
        f"> **Seed `{HOLDOUT_SEED}`, axis point `{HOLDOUT_AXIS_POINT}`, family",
        "> `datasets_gst_holdout`.** The seed was committed to",
        "> `corpus/SEEDS.txt` **before this dataset existed** and has never been",
        "> reselected; `corpus/datasets_gst_holdout/` was confirmed absent by a",
        "> failing `ls` immediately before generation (`DECISIONS.md` §64).",
        "> Generation produced 314 rows / 51 batches / 59 bank lines on the",
        "> first and only attempt.",
        ">",
        "> **Scored exactly once**, on 2026-08-31 (`DECISIONS.md` §64), against",
        "> code frozen by content hash before the data existed (§63). This file",
        "> is re-rendered from `corpus/gst_holdout_results.json` by",
        "> `corpus/render_gst_holdout.py`, which never calls `resolve()`,",
        "> `score_one()` or `corpus.oracle.score()`. **No number here has been",
        "> recomputed since that run**, and §68/§73 deliberately declined to",
        "> refresh it: the resolver would now answer slightly differently, which",
        "> is a reason to leave a held-out result alone, not to update it.",
        ">",
        "> **The §63 freeze, recomputed now:**",
        ">",
        "> | file | frozen at §63 | now |",
        "> |---|---|---|",
    ]
    for name, frozen in FROZEN_AT_63.items():
        path = ROOT / name
        if not path.exists():
            lines.append(f"> | `{name}` | `{frozen[:12]}…` | **MISSING** |")
            continue
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        state = ("unchanged" if current == frozen
                 else f"`{current[:12]}…` **changed after §64**")
        lines.append(f"> | `{name}` | `{frozen[:12]}…` | {state} |")
    lines += [
        ">",
        "> A file marked *changed after §64* is **not** a broken freeze. §63's",
        "> constraint ran until the held-out run had executed and reported;",
        "> §64 executed on 2026-08-31 and both subsequent changes came later",
        "> (`corpus/score_gst.py` via §65/§66, `resolver/loaders.py` via",
        "> §70–§72). The freeze expired as designed. This table is recomputed",
        "> on every render so that it states what is true today rather than",
        "> what was true when it was typed.",
        "",
    ]
    return "\n".join(lines)


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
    # The provenance block goes after the H1 so the title stays first.
    head, _, rest = text.partition("\n")
    text = head + "\n\n" + provenance_header() + rest
    OUT.write_text(text + "\n")
    RESULTS.write_text(json.dumps(results, indent=1) + "\n")
    print(f"rendered {OUT} from {RESULTS} -- no dataset re-scored")
    for r in results:
        print(f"  {r['dataset']}: oracle_passed={r['oracle_passed']} "
              f"itc_risk_flag={r.get('oracle_itc_risk_flag')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
