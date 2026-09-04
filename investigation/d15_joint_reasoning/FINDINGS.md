# D15's root cause: a measured, negative result on "extend consumption beyond `Verified`"

Diagnostic only. Nothing in `resolver/`, `resolver_contract/`, `matching/` or
`engine/` is touched. No dataset regenerated, no gate changed.

## 0. What this was trying to do

D15 (`CHECKPOINT.md` §12.4/§14.6, "the single most interesting open problem
this repository now contains") is the pool-inflation/consumption conflict: at
PSP absence, `Reconstructed` never calls `state.consumed.update(...)` (only
`Verified` does, contract §2.4/`may_consume()`), so the derived pool for
unattested reconstruction grows monotonically and destroys uniqueness on
later lines. Every straightforward fix has already been measured and
rejected — global ILP (`DECISIONS.md` §2, 1,347 booleans, `UNKNOWN` at 60s),
blind chronological reconstruction (§2, pool cascades to the enumeration
cap), column generation (`TECHNIQUES.md` §1, answers the wrong question), the
pseudopolynomial uniqueness oracle (§92, re-proves what's already proven),
date-window partitioning (`TECHNIQUES.md` §3, excludes the truth on >20% of
batches).

**What had never been measured**: whether `Reconstructed` itself — not
`Ambiguous`, not a contested claim — could safely consume. The stated reason
`may_consume()` withholds consumption from anything but `Verified` is about
*ambiguity* ("an ambiguity is not a reason to believe the rows are spent").
`Reconstructed` is not ambiguous by construction — its `__post_init__`
already requires `UNIQUE_CLOSURE_UNFILTERED` (exhaustive, unbiased — no
objective, contract §2.1) and `CROSS_LINE_EXCLUSIVITY`, and rejects
construction outright if independent corroboration exists (that would be
`Verified`). The stated justification does not obviously reach this case.

## 1. The hand proof, and the hole in it — both stated before the experiment ran

If `pool_at`'s superset guarantee holds (never wrongly excludes a row —
reaffirmed by F1/`DECISIONS.md` §45) and lines are processed in true
chronological order, induction says: the first line to report `Reconstructed`
must be correct (its true composition's rows were never falsely removed, so
if exactly one candidate closes, that candidate must be the truth — otherwise
the truth would be a second, distinct candidate, contradicting `count==1`).
Consuming it immediately should then only shrink later pools toward the
truth.

**The hole, named before running anything**: `resolve()` sorts credits by
`(value_date, line.index)` (`resolver/resolve.py:239`) — same-date lines are
ordered by an arbitrary index tiebreak, not true settlement order.
`_resolve_collisions`'s own docstring already records that two `Reconstructed`
claims colliding on a row "only showed up when the resolver was first run
across the whole corpus" under the current non-consuming regime — evidence
the tie risk is real.

## 2. The experiment

`track_eager_reconstruction.py` wraps `_tier_c` (monkeypatch only, no file
edited) so that a `Reconstructed` outcome calls
`state.consumed.update(outcome.assigned_rows)` immediately, in the same
chronological loop `resolve()` already runs. Every one of the 35 datasets
was re-resolved this way and diffed against the unmodified baseline,
checking every changed line's claimed rows against `ground_truth.json`.

```
total outcome-class changes: 3
total CORRECT recoveries:    2
total WRONG answers introduced: 1
```

**Zero changes on either D15 dataset** (`datasets/A20_Bnone_Cmax`,
`datasets/A40_Bnone_Cmax`) — this technique does not touch the coverage gap
it was aimed at, because almost none of D15's 15 correct-refusal lines ever
reach a first, uncontested `Reconstructed` to bootstrap from (12 of 13 on
`A20_Bnone_Cmax` hit the 200-candidate cap directly; see
`investigation/D15_MEASUREMENT.md` §2.2's table).

**One wrong answer, elsewhere, confirming the theoretical risk by a
different and more fundamental mechanism than the one predicted.**
`datasets_gst/A20_B100_Cmax_gst`, bank[50]: baseline `Unresolved`, eager
`Reconstructed`, claiming 9 rows including `pay_EKX47zkLpM7kSo` and
`pay_QsqWDyXfVREG1q`/`rfnd_4l3yZLv6EqN1m0`. Checked directly against the
dataset: those rows carry `settlement_id`s (`setl_f7kX3leajcF4ej`,
`setl_DrqBXAGvpqVPef`) belonging to two *other*, genuinely attested
settlements that bank[50] has no claim to. Consuming them broke those two
settlements' own attestation: bank[51] and bank[52] flip from `Verified`
(baseline, correct) to `AttestationDiscrepancy` (after) — a real regression,
not a relabeling.

**The actual mechanism is not the same-date tie predicted in §1.** It is
more fundamental: `pool_at` (`resolver/eligibility.py`) filters only on
`consumed`, the created-at ceiling, capture/T+2 eligibility, and
`net(row) != 0` — it does **not** exclude a row merely because it already
carries a `settlement_id` pointing to a different, not-yet-processed
settlement. Tier C's "no composition claim reaches this line" search
therefore treats every such row as fair game, and a coincidental subset-sum
match can make a factually-wrong reconstruction look "unique, complete,
exclusive" over its own pool — the exact shape of proof `Reconstructed`
requires, produced from a search space that was never supposed to include
those rows in the first place. This generalizes the risk found in §1: it is
not only same-date ties that can break the induction, but any row that is
attested-but-unprocessed at the moment tier C runs, on any date.

## 3. Verdict

**Rejected. This does not close D15's coverage gap (zero effect on the two
target datasets) and it is unsafe in general (measured, not assumed: one
confirmed regression on a dataset outside the target scope).** Joins the
table of already-measured-and-rejected directions in
`DECISIONS.md` (§2, `TECHNIQUES.md` §1/§3, §92) rather than sitting apart
from them as an untried idea. A safe version would need tier C's pool to
also exclude rows already carrying a `settlement_id` for an unprocessed
settlement — but that pool-narrowing move is exactly the class F1 (§45)
already measured as dangerous in the *opposite* direction (a narrower pool
once hid a real rival and let a wrong `Reconstructed` through), so it is not
a small follow-on fix; it would need its own full measurement pass, not
a quick patch here.

**D15 remains fully open.** The 1/24 PSP-absence coverage number is
unchanged. The already-shipped coverage-metric fix (`DECISIONS.md` §48,
`corpus/coverage.py`) already addresses the one adjacent, independently
fixable issue `investigation/D15_MEASUREMENT.md` found (coverage falling as
detection improves) — there is no further cheap, safe win identified in this
pass.

## Files

`track_eager_reconstruction.py` (the experiment, kept as evidence),
`eager_reconstruction_report.json` (full per-dataset output). No file under
`resolver/`, `resolver_contract/`, `matching/`, `engine/` or `corpus/` outside
this directory was touched.
