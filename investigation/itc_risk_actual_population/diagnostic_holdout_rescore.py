"""Diagnostic-only: what would the FIXED `_itc_risk_flag` report against the
held-out GST/ITC dataset? `DECISIONS.md` §88.

    python3 investigation/itc_risk_actual_population/diagnostic_holdout_rescore.py

## What this is NOT, and why that is the entire value

**This is not a re-score.** `corpus/GST_HOLDOUT_RESULTS.md` and
`corpus/gst_holdout_results.json` are the official, once-only held-out result
(`DECISIONS.md` §64, run 2026-08-31, frozen). Per §64/§65/§68/§73's five-entry
precedent chain, that file pair is NEVER re-scored, only ever re-rendered from
its own saved JSON. This script does not touch either of them: it never
imports `corpus.score_gst.score_one`, never opens any path under `corpus/` in
write mode, and writes its own output only under this directory. That claim is
checkable directly:

    grep -n "corpus/GST_HOLDOUT|gst_holdout_results|score_one|write_text.*corpus" \
        investigation/itc_risk_actual_population/diagnostic_holdout_rescore.py

and returns nothing but this docstring's own mentions of those names.

## What this IS

`DECISIONS.md` §88 fixed a structural bug in `corpus/oracle.py::
_itc_risk_flag`'s truth-set construction, diagnosed against §64's one false
negative (a refund counted as an at-risk payment). §64's own published number
-- precision 1.0 / recall 0.75 -- is not wrong; it correctly measured the
resolver against the OLD, buggy definition of `actual`. This script answers a
different question: what does the CORRECTED definition report, against the
exact same frozen dataset? It exists so that question is answerable without
ever touching the official artifact.

It is safe to run `resolve()` again against this dataset for this diagnostic
purpose because `DECISIONS.md` §68 proved it byte-identical across repeated
calls -- zero clock-stops, confirmed via
`investigation/resolver_nondeterminism/`'s own before/after captures -- and
because there is direct precedent for doing exactly this: both
`investigation/resolver_nondeterminism/PREDICTION.md`'s and §68's own
`determinism_probe.py`/`contended_probe.py` ran diagnostic `resolve()` calls
against this identical dataset, pre-fix, without that counting as a re-score.

This run happens under everything CURRENT -- post-§68 (deterministic budget),
post-§73 (loader fixes) -- not the exact conditions §64 ran under. That
mismatch is disclosed in the output, not smoothed over.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.oracle import _itc_risk_flag                             # noqa: E402
from resolver.loaders import load                                    # noqa: E402
from resolver.resolve import resolve                                 # noqa: E402

TARGET = ROOT / "corpus" / "datasets_gst_holdout" / "A20_B100_Cmax_gst_holdout"
HERE = Path(__file__).resolve().parent

#: §64's officially published, frozen figures. Quoted, never recomputed, so
#: the diagnostic output below can cite them by reference rather than by
#: re-deriving something that might silently drift from what was published.
OFFICIAL_S64 = {
    "true_positive": 3, "false_positive": 0, "false_negative": 1,
    "precision": 1.0, "recall": 0.75,
}


def main() -> int:
    if not TARGET.exists():
        print(f"{TARGET} does not exist", file=sys.stderr)
        return 1

    truth = json.loads((TARGET / "ground_truth.json").read_text())
    dataset = load(TARGET)
    output = resolve(dataset)

    result = _itc_risk_flag(output, truth)

    payload = {
        "label": "DIAGNOSTIC ONLY -- not a re-score of DECISIONS.md sec 64. "
                 "corpus/GST_HOLDOUT_RESULTS.md and "
                 "corpus/gst_holdout_results.json are unchanged.",
        "dataset": "datasets_gst_holdout/A20_B100_Cmax_gst_holdout",
        "official_sec64": OFFICIAL_S64,
        "corrected_under_sec82": {
            k: result[k] for k in
            ("true_positive", "false_positive", "false_negative",
             "precision", "recall", "open_break_rows",
             "open_break_rows_payment_type", "open_break_rows_settled_in_truth")
        },
        "prediction_from_PREDICTION_md_section_4": {
            "true_positive": 3, "false_positive": 0, "false_negative": 0,
        },
        "prediction_held": (
            result["true_positive"] == 3 and result["false_positive"] == 0
            and result["false_negative"] == 0),
    }

    out_json = HERE / "holdout_diagnostic_result.json"
    out_json.write_text(json.dumps(payload, indent=2) + "\n")

    md = [
        "# Diagnostic re-run against the held-out GST/ITC dataset -- NOT a re-score",
        "",
        "**`corpus/GST_HOLDOUT_RESULTS.md` and `corpus/gst_holdout_results.json`",
        "are unchanged by this document.** `DECISIONS.md` §64's officially",
        "published figures stand exactly as published:",
        "",
        f"> TP={OFFICIAL_S64['true_positive']}, "
        f"FP={OFFICIAL_S64['false_positive']}, "
        f"FN={OFFICIAL_S64['false_negative']}, "
        f"precision={OFFICIAL_S64['precision']}, "
        f"recall={OFFICIAL_S64['recall']}",
        "",
        "This document answers a different question: what does §88's CORRECTED",
        "`_itc_risk_flag` report against the same frozen dataset, re-run today?",
        "The old number was not wrong -- it correctly measured the resolver",
        "against the old definition of `actual`. This is what the new",
        "definition measures.",
        "",
        "Run under everything current as of this script's execution -- post-§68",
        "(deterministic CP-SAT budget), post-§73 (loader fixes) -- not the exact",
        "conditions §64 ran under. That mismatch is disclosed, not smoothed over.",
        "",
        "| | official (§64, frozen) | diagnostic (§88, today) |",
        "|---|---:|---:|",
        f"| true_positive | {OFFICIAL_S64['true_positive']} | "
        f"{result['true_positive']} |",
        f"| false_positive | {OFFICIAL_S64['false_positive']} | "
        f"{result['false_positive']} |",
        f"| false_negative | {OFFICIAL_S64['false_negative']} | "
        f"{result['false_negative']} |",
        f"| precision | {OFFICIAL_S64['precision']} | {result['precision']} |",
        f"| recall | {OFFICIAL_S64['recall']} | {result['recall']} |",
        "",
        f"**§88's prediction §4 forecast TP=3/FP=0/FN=0 without having",
        f"enumerated every row in this dataset's universe by type first, and",
        f"named itself falsified if the enumeration found otherwise.** Measured",
        f"result: prediction {'HELD' if payload['prediction_held'] else 'FAILED -- reported as a miss, not revised'}.",
        "",
        f"`open_break_rows`: {result['open_break_rows']} total, "
        f"{result['open_break_rows_payment_type']} of them payment-type, "
        f"{result['open_break_rows_settled_in_truth']} settled in truth.",
    ]
    (HERE / "HOLDOUT_DIAGNOSTIC.md").write_text("\n".join(md) + "\n")

    print(f"prediction held: {payload['prediction_held']}")
    print(json.dumps(payload["corrected_under_sec82"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
