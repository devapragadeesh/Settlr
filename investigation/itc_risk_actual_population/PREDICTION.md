# Prediction, written before `corpus/oracle.py` is touched

This is the fix for the defect diagnosed against `DECISIONS.md` §64's held-out
GST/ITC result: `precision 1.0 / recall 0.75`, one false negative. Committed in
its own commit, **before** any line of `corpus/oracle.py` changes, so the
ordering is verifiable from `git log` rather than asserted in prose — the same
discipline `investigation/resolver_nondeterminism/PREDICTION.md` used for §67.

## Why this one needs more rigor than that precedent, not less

§67's fix (the resolver's wall-clock budget) was motivated by a mechanical
property — reproducibility — unrelated to any specific accuracy number. §61's
fix (the resolver-side ancestor of this bug) predated any held-out run
entirely. **This fix is different: its entire motivation is a specific number
already on the record**, and §64 itself pre-emptively named the move this
entry must not be: *"Rejected: fixing the recall-0.75 gap now that it's
visible... it does not permit fixing resolver/ or corpus/oracle.py in response
to a score, however tempting a single false negative is to chase."*

That sentence is answered directly, not routed around, in four ways stated
below and checked, not asserted: the bug is diagnosable from two functions
alone with no dataset in hand; the fix is a structural ceiling that cannot
reach further than the diagnosed defect even if it were pointed at the score;
the blast radius on every dataset an implementer could have iterated against
is measured here, before the fix, to be exactly zero; and the held-out
artifact is never touched by anything in this cycle.

## 1. The bug, stated precisely

`corpus/oracle.py::_itc_risk_flag` (function starts at line 670) builds a
truth set at lines 749-761:

```python
universe = sorted({row_id for item in output.open_breaks
                   for row_id in item.row_ids})
...
actual = {(row_id, ground) for row_id in universe
          for ground in at_risk.get(truth_month(row_id) or "", ())}
```

`universe` is every row appearing in any `OpenBreak`, of any TYPE — payment,
refund, or adjustment. `actual` crosses that whole set against every
statutory ground active in the row's settled month, with no check that the
row itself could have generated a gateway fee. The oracle measures the
resolver against a truth population the resolver's own contract does not
recognise as at-risk in the first place.

This is the same shape `DECISIONS.md` §61 already fixed once, on the
**resolver** side: `resolver/breaks.py::_accrues_input_tax` (lines 154-186,
read in full before writing this prediction) requires

```python
return bool(row["type"] == "payment"
            and row.get("settled_at")
            and row.get("fee")
            and row.get("tax"))
```

before a row may carry ITC risk. Its own docstring names the identical
mechanism: *"a refund or an adjustment is not a supply the gateway
invoices for."* The oracle's `actual` was never given the equivalent guard.
This is diagnosable by reading those two functions side by side, with no
corpus and no held-out score in hand at all — the same standalone-correctness
argument §61 made for its own fix.

**Concretely, the one instance this has ever produced a visible effect:** the
held-out dataset's false negative, `rfnd_bJNvTaslE4EpW0` — a refund, which
carries no gateway fee and hence no input tax at risk. The resolver correctly
declined to flag it. `actual` counted it as a true finding because it merely
settled into an at-risk month.

## 2. The hard ceiling, stated before any code exists

**The fix below can replicate only the `type == "payment"` leg of
`_accrues_input_tax`. It cannot replicate the `settled_at`, `fee`, or `tax`
legs**, because `corpus/oracle.py::score()` receives only a `ResolverOutput`
and the parsed `ground_truth.json` dict — never the resolver's `Dataset`,
never any row's `fee` or `tax` field. Verified now, not assumed:

```
$ grep -n '"fee"\|"tax"\|\.rows\b' corpus/oracle.py
(zero matches)
```

`ground_truth.json`'s top-level keys carry no `rows` block and no per-row tax
field anywhere (`attestation, axes, axis_point, bank_diagnostics, bank_lines,
batches, contract, determined_instances, erp_orphan_invoices,
gateway_fee_invoices, gateway_gstin, generated_by, gst_rounding_residuals,
gst_truth, itc_at_risk, merchant_gstin, netted_out,
payments_missing_from_erp, planted_classes, provenance, roles, seed,
settled_in, spec, unsettled_reason, warning`).

This is stated as a **ceiling the fix is sized to**, not a caveat added after
the fact. Plumbing the resolver's `Dataset` into `oracle.score()` so `actual`
could also gate on `fee`/`tax` is explicitly out of scope (§6) — doing that
now, in direct response to the held-out score, would be far closer to the
forbidden tuning pattern than the type-only fix is, because it would visibly
widen the fix's reach specifically because a number was seen. The type-only
fix cannot be widened that way even if someone wanted to.

**The only signal recoverable for row type at all** is the id-prefix
convention `corpus/generator/build.py` mints rows under
(`pay_`/`rfnd_`/`adj_`, lines 386/409/429) — not an asserted contract
anywhere in `corpus/oracle.py` today. A conformance test pins it against a
real generated fixture in the fix commit, so a future drift in the naming
convention fails loudly rather than silently degrading this predicate into a
no-op or an over-broad filter.

## 3. Blast radius, measured now, before the fix exists

**Claim: on both live-scored spine datasets, this fix changes nothing.**
Checked directly against the currently-committed `corpus/gst_results.json`:

```
datasets_gst/A20_B100_Cmax_gst        -> TP=0 FP=0 FN=0 precision=None recall=None  (open_break_rows=22)
datasets_gst/A20_B100_Cmax_gst_noisy  -> TP=0 FP=0 FN=0 precision=None recall=None  (open_break_rows=18)
```

The entire at-risk-and-open subpopulation is empty on both — `predicted` and
`actual` are both already `∅`. A stricter `actual` can only ever *remove*
pairs from an already-empty set, so these two numbers are **provably
unchanged** by this fix. *Falsified by:* any nonzero diff in either dataset's
`itc_risk_flag` block after regeneration (§5 below states the exact
verification).

**G10 (§76)** reads `false_positive = |predicted − actual|`. Since `predicted`
is also empty on both live datasets, `predicted − actual = ∅` regardless of
how `actual` is constructed — **this fix cannot flip any G10 verdict that is
currently computed.** Flagged as a directional risk for *future* datasets
only: a stricter `actual` can only ever *increase* `false_positive` on some
dataset where `predicted` contains a pair no longer in `actual`, never
decrease it. Nothing in this pass resolves that risk; it is named so it is
not rediscovered as a surprise later.

**The held-out dataset is the only place this bug has ever had a visible,
nonzero effect.** Every other measured dataset in the corpus either carries
no `gst_truth` at all, or (per the two datasets above) has an empty
subpopulation. This is why the blast radius on everything an implementer
*could* have iterated against — the live-scored family — is provably zero:
there was nothing there to tune against.

## 4. What happens to the held-out number — predicted, not yet run

Hand-derived from the diagnosed defect alone, **without running anything new
against the frozen JSON**: with the `type == "payment"` filter applied to
`universe`, the refund `rfnd_bJNvTaslE4EpW0` drops out, which was the sole
named source of the false negative. Predicted: `TP=3, FP=0, FN=0` —
precision 1.0 / recall 1.0 — **if and only if no other refund or adjustment
row in that dataset's `universe` was contributing an as-yet-invisible false
negative or true positive of its own.**

**I have not enumerated every row in that dataset's `universe` by type before
writing this prediction.** That enumeration is exactly what the diagnostic
script (§5) performs. If it turns up more than the one known refund, this
prediction is **falsified and reported as a miss**, not quietly revised to
match whatever the script finds.

*Falsified by:* the diagnostic script reporting `TP != 3` or `FP != 0` or
`FN != 0`.

**This is deliberately not a claim that recall "should" be 1.0 in some
normative sense**, and not a claim that the resolver's own fee/tax gate is
validated by this. It is a claim about what removing one already-diagnosed
structural bug does to one already-published number, computed by hand-tracing
the fix against the one row already named in the defect report — the same
scope §61 held to when it predicted the spine dataset would go from 4 false
positives to 0.

## 5. Exactly how the held-out figure is produced, and how it cannot be
   mistaken for a re-score

`investigation/itc_risk_actual_population/diagnostic_holdout_rescore.py`
(committed alongside the fix, not in this prediction commit):

1. Loads `corpus/datasets_gst_holdout/A20_B100_Cmax_gst_holdout` via
   `resolver/loaders.py::load()`.
2. Calls `resolver/resolve.py::resolve()` on it **once**, diagnostic only.
   Safe and reproducible only because §68 proved this exact dataset has zero
   clock-stops and is byte-identical across repeated `resolve()` calls
   (`investigation/resolver_nondeterminism/`'s own before/after captures).
   There is direct precedent for exactly this move — a diagnostic `resolve()`
   against this dataset that is not a re-score —
   `investigation/resolver_nondeterminism/PREDICTION.md`'s and §68's own
   `determinism_probe.py`/`contended_probe.py` did it twice already, pre-fix.
3. Calls the **fixed** `_itc_risk_flag(output, truth)` against that output
   and the dataset's own `ground_truth.json`.
4. Writes `holdout_diagnostic_result.json` and `HOLDOUT_DIAGNOSTIC.md` —
   **both under `investigation/`, never under `corpus/`.** The script never
   imports `corpus.score_gst.score_one` and never opens any path under
   `corpus/` in write mode — checkable by grep, and its own docstring states
   this explicitly, mirroring `corpus/render_gst_holdout.py`'s "what this
   does NOT do, and why that is the entire value."
5. `HOLDOUT_DIAGNOSTIC.md`'s title states plainly it is not a re-score. It
   cites §64's `TP=3/FP=0/FN=1, precision 1.0/recall 0.75` by reference,
   quoting the entry number and the numbers verbatim, rather than restating
   them as superseded. It presents the new numbers side-by-side, explicitly
   labeled diagnostic, and discloses — rather than smooths over — that this
   run happens under everything current (post-§68, post-§73), not the exact
   conditions §64 ran under.

**`corpus/GST_HOLDOUT_RESULTS.md` and `corpus/gst_holdout_results.json` are
not touched by any step in this cycle.** §64's published number stands
exactly as published, unedited, forever. Fixing the oracle's definition of
`actual` does not retroactively make the old number wrong — 0.75 was a true,
correctly-computed statement about what the resolver did against the *old*
definition. The fix changes what future runs measure, not the truth of what
was measured before.

## 6. Downstream figures, named now

**DOES recompute:**
- `corpus/GST_RESULTS.md` / `corpus/gst_results.json` — via a plain
  `score_gst.py --all` run against the live spine datasets. Predicted
  byte-identical on every `itc_risk_flag` figure (§3), plus one new additive
  key (`open_break_rows_payment_type`).
- `investigation/itc_risk_actual_population/holdout_diagnostic_result.json`
  and `HOLDOUT_DIAGNOSTIC.md` — new, diagnostic-only, not scoring artifacts.

**Does NOT recompute:**
- `corpus/GST_HOLDOUT_RESULTS.md`
- `corpus/gst_holdout_results.json`

Named explicitly in this column, not by omission, per §65/§68/§73's own
standing convention for this exact file pair.

## 7. What this prediction does not touch

No line of `resolver/breaks.py` changes. No line of `resolver_contract/`
changes. Nothing here gates the corrected recall — §76 already declined to
gate recall over a four-row population, and this pass gives no reason to
revisit that. These are stated here, before the fix, as boundaries the fix
commit must not cross.
