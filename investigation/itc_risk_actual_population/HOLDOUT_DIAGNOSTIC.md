# Diagnostic re-run against the held-out GST/ITC dataset -- NOT a re-score

**`corpus/GST_HOLDOUT_RESULTS.md` and `corpus/gst_holdout_results.json`
are unchanged by this document.** `DECISIONS.md` §64's officially
published figures stand exactly as published:

> TP=3, FP=0, FN=1, precision=1.0, recall=0.75

This document answers a different question: what does §88's CORRECTED
`_itc_risk_flag` report against the same frozen dataset, re-run today?
The old number was not wrong -- it correctly measured the resolver
against the old definition of `actual`. This is what the new
definition measures.

Run under everything current as of this script's execution -- post-§68
(deterministic CP-SAT budget), post-§73 (loader fixes) -- not the exact
conditions §64 ran under. That mismatch is disclosed, not smoothed over.

| | official (§64, frozen) | diagnostic (§88, today) |
|---|---:|---:|
| true_positive | 3 | 3 |
| false_positive | 0 | 0 |
| false_negative | 1 | 0 |
| precision | 1.0 | 1.0 |
| recall | 0.75 | 1.0 |

**§88's prediction §4 forecast TP=3/FP=0/FN=0 without having
enumerated every row in this dataset's universe by type first, and
named itself falsified if the enumeration found otherwise.** Measured
result: prediction HELD.

`open_break_rows`: 16 total, 13 of them payment-type, 4 settled in truth.
