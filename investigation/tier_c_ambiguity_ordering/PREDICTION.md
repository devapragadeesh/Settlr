# Prediction, written before `resolver/resolve.py` is touched

This is the fix for a bug found while investigating D15 (PSP-absent
coverage): `resolver/resolve.py::_tier_c` checks `not closures.complete`
*before* `closures.count > 1`, so a truncated enumeration that already found
≥2 distinct closing subsets — definitive, already-proven non-uniqueness — is
reported as `Unresolved(ENUMERATION_TRUNCATED)` instead of the more
informative `Ambiguous`. Committed in its own commit, **before** any line of
`resolver/resolve.py` changes, so the ordering is verifiable from `git log`
rather than asserted in prose — the same discipline `investigation/
resolver_nondeterminism/PREDICTION.md` (§67) and `investigation/
itc_risk_actual_population/PREDICTION.md` (§88) used.

## What this is not

**This does not close D15's 1/24 PSP-absence coverage number.** No line moves
to `Reconstructed`/`Verified`. `investigation/D15_MEASUREMENT.md` already
proved the 15 correct-refusal lines on the two PSP-absence datasets are
genuinely non-unique over the resolver's derived pool — this fix does not
touch the pool, does not touch consumption, and does not make any line more
determinable than it already was. It converts silent, unproven abstention
(`Unresolved`, "we don't know") into honest, evidenced abstention
(`Ambiguous`, "we know, and here's the proof"), on lines that were always
going to abstain. **The D15 datasets will still fail G8 after this fix**,
exactly as before — verified directly against
`resolver_contract/types.py::abstention_failures` (below).

The deep fix — the pool-inflation/consumption conflict named repeatedly in
`CHECKPOINT.md` §12.4/§14.6 and `DECISIONS.md` §46 as "the single most
interesting open problem" this repo contains — is not attempted here. A
pseudopolynomial uniqueness oracle (`corpus/TECHNIQUES.md`'s assessed-but-
unbuilt direction) is not attempted here either: verified below that it
would not change coverage.

## 1. The bug, stated precisely

`resolver/resolve.py::_tier_c`, current order:

```python
if closures.count == 0:
    ...  # unchanged by this fix

if not closures.complete:                    # <-- fires first
    return Unresolved(reason=ENUMERATION_TRUNCATED,
                      partial_candidates=_candidate_set(closures, ...), ...)

if closures.count > 1:                        # <-- never reached when truncated
    return Ambiguous(candidate_set=_candidate_set(closures, ...), ...)
```

Non-uniqueness needs only ≥2 witnesses, proven the instant a second closing
subset is found — completeness is never required to disprove uniqueness,
only to prove it. `_tier_c` collapses this distinction: any truncation routes
to `Unresolved` regardless of how many rivals were already found before the
clock or cap stopped the search.

**Verified safe against `resolver_contract/types.py` directly, zero contract
change needed:**

```
$ grep -n "class Ambiguous" -A 20 resolver_contract/types.py
```
`Ambiguous.__post_init__` requires only `candidate_set.size >= 2` — no
completeness requirement.

```
$ grep -n "class CandidateSet" -A 20 resolver_contract/types.py
```
`CandidateSet`'s own docstring: *"`complete=False` means enumeration stopped
early. The set is then a SAMPLE and the line is MORE ambiguous than its
length suggests, never less. It is still reported in full..."* — this
already anticipates and endorses exactly the case this fix constructs.
`_candidate_set(closures, rows_by_id)` (`resolve.py:161-166`) already
propagates `closures.complete` into `CandidateSet.complete`, so an
`Ambiguous` built from a truncated `closures` is automatically, correctly
labelled a sample with zero new plumbing.

**The original comment's intent is preserved exactly.** *"One found under
truncation is NOT uniqueness"* guards against promoting a truncated
*single*-solution find to `Reconstructed` — §39's defect class. This fix
does not touch that: `count == 1` truncated still falls through to the
(now second) `not complete` check and still returns
`Unresolved(ENUMERATION_TRUNCATED)`, unchanged. Only the `count > 1`
truncated case is rerouted.

## 2. Why a pseudopolynomial uniqueness oracle would not close coverage

`corpus/TECHNIQUES.md` names, but does not build, an algorithm to prove
`≥2 closing subsets exist` cheaper than full enumeration. Checked directly
against measured data before writing this prediction: of the 12 truncated
lines on `datasets/A20_Bnone_Cmax` and 15 on `datasets/A40_Bnone_Cmax` that
this fix reclassifies, every one already has `candidate_count >= 8` (most at
the 200-solution cap) — **non-uniqueness was already proven by the existing
CP-SAT run before it truncated.** A faster or better-certified algorithm
would reach the same negative verdict more cheaply; it would not change
which lines are unique, because none of these lines are unique. This
technique is not part of this fix.

## 3. Blast radius, measured now, before the fix exists

`investigation/tier_c_ambiguity_ordering/sweep_truncation_reclass.py` wraps
`resolver.resolve._tier_c` directly (not `closing_subsets`) so each call is
attributed to an exact `bank_index`, and cross-references every
`Unresolved(ENUMERATION_TRUNCATED)` outcome's `partial_candidates.size`
against `>1`. Run against the current, unfixed code, across all 35 datasets:

```
93 total (dataset, bank_index) pairs predicted to flip
Unresolved(ENUMERATION_TRUNCATED) -> Ambiguous, across 28 of 35 datasets
```

**This is far broader than the two PSP-absence datasets** — full detail in
`investigation/tier_c_ambiguity_ordering/predicted_reclassification.json`.
The two D15 datasets, exactly:

```
datasets/A20_Bnone_Cmax  — 12 of 13 truncated Unresolved lines flip
  bank[5]  count=200 (cap)     bank[6]  count=200 (cap)
  bank[7]  count=200 (cap)     bank[8]  count=9
  bank[9]  count=9             bank[10] count=200 (cap)
  bank[11] count=20            bank[12] count=200 (cap)
  bank[14] count=200 (cap)     bank[15] count=8
  bank[16] count=200 (cap)     bank[17] count=200 (cap)

  (bank[0] is Reconstructed, bank[18] is AttestationDiscrepancy -- the two
  non-abstentions D15_MEASUREMENT.md already named. bank[13] is
  Unresolved(NOT_OUR_CREDIT), a different reason entirely, never a candidate
  for reclassification -- verified directly, not presumed.)

datasets/A40_Bnone_Cmax — 15 of 15 truncated Unresolved lines flip, ALL of
  them, every one at count=200 except bank[3] at count=24
```

Every reclassified count exceeds `1`, most by a wide margin (200 = the
enumeration cap). *Falsified by:* the post-fix sweep finding any
`(dataset, bank_index)` pair outside this set flipping class, or any pair
inside this set NOT flipping.

**This is a fresh measurement, not a reuse of `investigation/
D15_MEASUREMENT.md`'s older table.** That table predates §68's determinism
fix; reusing it uncritically here would repeat exactly the "measurement
taken with a broken instrument" mistake §68's own claim 1 caught itself
making. The sweep script asserts, per dataset, that two independent
`resolve()` calls against the unfixed code agree on every outcome class
before trusting either — confirming this measurement's own premise
(deterministic `closing_subsets`, already established by §68) rather than
assuming it.

## 4. The prediction

1. **Exactly the 93 `(dataset, bank_index)` pairs listed in
   `predicted_reclassification.json` flip `Unresolved(ENUMERATION_TRUNCATED)
   → Ambiguous`.** Every other line, on every dataset, is byte-identical
   before and after. *Falsified by:* any flip outside this set, any pair in
   this set not flipping, or any outcome-class change of any other shape
   (e.g. anything becoming `Reconstructed`/`Verified`, which this fix cannot
   produce by construction — it only intercepts the `count > 1` branch).
2. **No composition changes anywhere.** `composition` exists only on
   `Verified`/`Reconstructed`, neither of which this fix's code path
   touches. *Falsified by:* any composition diff.
3. **No G-gate flips.** Verified from code, not asserted: `resolver_contract/
   types.py::abstention_failures` (lines ~1199-1223) appends to its failures
   list identically whether `isinstance(outcome, Unresolved)` or
   `isinstance(outcome, Ambiguous)` — a line already a G7/G8 failure stays
   one; a line that was not a `determined`/`reconstructible` member is
   unaffected either way. G3 (`corpus/oracle.py:327-356`) reads
   `outcome.candidate_set` for `Ambiguous` and `outcome.partial_candidates`
   for a truncated `Unresolved` — the same `CandidateSet` object either way,
   since `_candidate_set(closures, ...)` is called identically on both
   paths today. *Falsified by:* any gate's violation count or dataset
   pass/fail verdict changing.
4. **The D15 datasets still fail G8 after the fix, with the same violation
   count.** Named explicitly so no reader mistakes this for a coverage
   improvement. *Falsified by:* either dataset's G8 count changing.

**What I do NOT predict:** which direction `mean_candidate_set_size`/
`max_candidate_set_size` move per dataset in `corpus/oracle_results.json` —
the population of candidate-set sizes feeding those statistics changes (some
now drawn from `Ambiguous.candidate_set` rather than
`Unresolved.partial_candidates`, both already the same object, so the
statistic's *value* should be identical if it already summed over both
sources — this is checked in §5's verification, not assumed here).

## 5. Downstream figures to recompute, named now

**DOES recompute:** `corpus/ORACLE_RESULTS.md`/`oracle_results.json`,
`corpus/THREE_SYSTEMS.md`, `CLAIMS.md`, `SCORECARD.md`, `dashboard/data.json`
(via `corpus/export_dashboard.py`), and `corpus/GST_RESULTS.md`/
`gst_results.json` if the sweep shows any `datasets_gst/*` line affected —
checked directly above: **zero** `datasets_gst/*` lines are in the predicted
set, so this step is run to confirm-no-diff, not because a diff is expected.

**Does NOT recompute:** `corpus/GST_HOLDOUT_RESULTS.md`/
`gst_holdout_results.json`. Checked directly above: **zero**
`datasets_gst_holdout/*` lines are in the predicted set — this fix cannot
reach that dataset. A diagnostic reach-check (loads the dataset, calls
`resolve()` once, asserts zero `_tier_c` truncation) confirms this
positively rather than by inference, per §88's precedent, without ever
opening either held-out file in write mode.

`corpus/baseline_results.json` is not re-run: `matching/` and `engine/` are
untouched by this change.
