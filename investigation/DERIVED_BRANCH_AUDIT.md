# DERIVED BRANCH AUDIT

What the `CorrectlyUnmatched` derived branch may be permitted to claim once
Part 2 splits the outcome into `ProvenUnmatched` and `OpenBreak`.

Diagnosis only. Nothing under `resolver/`, `resolver_contract/`, `corpus/` or
any frozen path was modified to produce this. Every count is a full
enumeration over all 30 datasets — 4,994 `CorrectlyUnmatched` claims — not a
sample.

Input: the Part 1 finding that `CorrectlyUnmatched` is 45.7% accurate overall
(2,283 of 4,994), splitting into a positively derived branch at 97.6%
(1,828/1,872) and a residual fallthrough at 14.6% (455/3,122).

---

## 0. Lead with what is worse than expected

**Correcting the derivations makes the reasons more accurate and the G9 gate
dramatically worse.** Transcribing the frozen `engine/simulator.py` predicates
exactly takes wrong reasons from 36 down to 10, and takes rows that *actually
settled* inside the derived branch from **8 up to 64**.

The mechanism is not subtle. The corrected `dispute_held` test pulls 142 rows
out of the `rolled_forward` residual and into a derived branch. Under today's
code those rows assert nothing that gets scored. Promoted into a derived
branch they become positive false claims. **A more accurate classifier is a
more dangerous one, because accuracy was never the property `ProvenUnmatched`
needs.**

The property it needs is *entailment*, and two of the four derived reasons do
not have it at any level of implementation quality:

| reason | 64 counterexamples say |
|---|---|
| `dispute_held` | a hold at the horizon does **not** entail the row never settled — the hold is released and the row settles later |
| `not_yet_eligible` | "not eligible in this window" is a statement about the window, not about the row |

`ROLLED_FORWARD` was specified as a residual and shipped as one. Promoting
`dispute_held` into `ProvenUnmatched` because it reads a status field and
scores 90% would be the same mistake with better manners.

**Second finding, unexpected.** The recon file's `on_hold` column is a
*current-state snapshot*; the correct question is whether the row was held
*at the settlement horizon*. Those disagree for **202 of 540 disputed rows
(37.4%)** — 186 where the column says not-held but the dispute opened before
the horizon, 16 the other way. This is the same defect class as the
mislabelled `complete` flag (`CHECKPOINT.md` §6.6): a point-in-time fact read
as a timeless one.

---

## 1. The 8 `netted_out` rows that actually settled

All 8 rows descend from just **4 payments**, and all 4 have the identical
shape: refund #1 equals the gross amount exactly and lands before
`eligible_at`; refund #2 is an *additional, later* refund that pushes the
refunded total above the gross.

| # | row | type | dataset | payment | amount | Σ refund debits | settled into (truth) |
|---|---|---|---|---|---:|---:|---|
| 1 | `pay_raKylPP1xmrYJP` | payment | `datasets/A40_Bnone_Cmax` | itself | 130,000 | 162,500 | `setl_tzifAkKFWm7MEu` |
| 2 | `rfnd_mMSauJ8GaS7qR0` | refund | `datasets/A40_Bnone_Cmax` | `pay_raKylPP1xmrYJP` | 130,000 | 162,500 | `setl_tzifAkKFWm7MEu` |
| 3 | `rfnd_sZtkfAEojsfCkY` | refund | `datasets/A40_Bnone_Cmax` | `pay_raKylPP1xmrYJP` | 130,000 | 162,500 | `setl_17Rn9DW5fVg5iO` |
| 4 | `pay_oderzlol4kf2Ht` | payment | `datasets_v2/A20_B100_Cmax` | itself | 134,500 | 201,700 | `setl_YNIQZOosnFdCB2` |
| 5 | `rfnd_EAyICVMrdXuf4a` | refund | `datasets_v2/A20_B100_Cmax` | `pay_oderzlol4kf2Ht` | 134,500 | 201,700 | `setl_YNIQZOosnFdCB2` |
| 6 | `rfnd_rUNhbGTPAY6as6` | refund | `datasets_v2/A20_B100_Crandom0` | `pay_4BD0laGF6cU4Ms` | 749,700 | 937,100 | `setl_ceGDUBOFNYw2E5` |
| 7 | `pay_ncBDZFvlLy7Sdj` | payment | `datasets_v2/A60_B100_Cmax` | itself | 145,000 | 193,300 | `setl_H6w4THt1vskuS2` |
| 8 | `rfnd_z8jmqQ034QC99L` | refund | `datasets_v2/A60_B100_Cmax` | `pay_ncBDZFvlLy7Sdj` | 145,000 | 193,300 | `setl_H6w4THt1vskuS2` |

Worked example, row 4/5 (`datasets_v2/A20_B100_Cmax`):

```
pay_oderzlol4kf2Ht   amount 134,500   credit (net of 3,175 fee) 131,325
  created_at   2027-03-20 07:30:29 IST
  eligible_at  2027-03-23 11:00:00 IST
  rfnd_EAyICVMrdXuf4a  debit 134,500  at 2027-03-21 07:07  BEFORE eligible_at
  rfnd_cWn0R0yFZv8aw7  debit  67,200  at 2027-04-01 07:30  AFTER  eligible_at
  Σ debits 201,700

resolver test : 201,700 >= 131,325            -> True   "netted out"
frozen  test  : 201,700 == 134,500 -> False           ) both must hold
                all refunds <= eligible_at -> False   )
truth         : the payment AND rfnd_EAyICVMrdXuf4a both settled in
                setl_YNIQZOosnFdCB2 (net effect -3,175, the fee)
```

### 1.3 Which case is it

`engine/simulator.py:366-376` is the normative rule:

```python
if sum(r.amount for r in rs) == p.amount and all(
    r.created_at <= eligible_at[p.id] for r in rs
):
```

`resolver/resolve.py:_unmatched_reason` diverges from it in **three
independent ways**, and each one alone would have caught all 8 rows:

| # | frozen rule | resolver | case |
|---|---|---|---|
| 1 | `== p.amount` | `>= row["credit"]` — inequality, not equality | (a) partial/excess misread as full |
| 2 | compares against **gross** `amount` | compares against **net** `credit` (amount − fee) | (a) wrong base; every refund of ≥ amount−fee passes |
| 3 | `all(r.created_at <= eligible_at)` | **no timing test at all** | (b) post-eligibility refunds counted |

Case (c) — aggregation over multiple refunds — *is* handled: both
implementations sum. It is the aggregate that exposes the other three.
Cases (d) and (e) do not arise: no refund is failed, and the spec models this
shape correctly at `SETTLEMENT_SPEC.md` §3, which states plainly that a
partially refunded payment "settles at **full** `amount − fee`" and that "any
refund after the payment settled" is a debit row in a later batch.

### 1.4 Verdict: FIXABLE

This is a transcription error, not an inherent limitation. Both inputs —
refund amounts and `created_at` — are merchant-visible in the recon feed.
Transcribing the frozen predicate exactly takes `netted_out` to **484 rows,
0 settled, 0 wrong reasons** (from 506 / 8 settled / 14 wrong).

`netted_out` **can** support a zero-tolerance claim once corrected.

---

## 2. The 21 `dispute_held` wrong reasons

**All 21 are the same mechanism, unanimously.** Not one is a precedence
conflict in the sense anticipated.

Every one of the 21 has truth `not_yet_eligible_at_horizon`, and in every one
of the 21 the dispute **opened after the last batch was formed**:

```
horizon (last batch formed_at)  = 2027-03-24 17:00 IST   in all 30 datasets
earliest offending dispute      = 2027-03-24 20:56 IST   (pay_rFqN9TWx3htxUC)
latest                          = 2027-03-31 03:49 IST   (pay_xGC94AluzRrWy0)
```

`engine/simulator.py:382-385` defines the hold as time-parameterised —
`hold_from <= t < hold_until` — and evaluates it at the horizon. At that
instant none of these 21 payments was held, so the frozen rule falls through
to `eligible_at > horizon`. The resolver instead reads the recon file's static
`on_hold` boolean, which reflects the state at *export* time, days later.

Full enumeration, all 21 (dispute phase/status is `under_review` in every
case; `amount_deducted = 0` in every case):

| # | row | dataset | dispute opened | eligible_at |
|---|---|---|---|---|
| 1 | `pay_UhnuZ0WqOpmkSW` | `datasets/A20_B100_Cfifo` | 03-26 07:24 | 03-29 11:00 |
| 2 | `pay_aE3vsYcs3jPGBZ` | `datasets/A20_B100_Crandom0` | 03-27 08:53 | 03-29 11:00 |
| 3 | `pay_nRnUiHnHywH08C` | `datasets/A20_B100_Crandom0` | 03-26 04:03 | 03-30 11:00 |
| 4 | `pay_xGC94AluzRrWy0` | `datasets/A20_B50_Cmax` | 03-31 03:49 | 03-31 11:00 |
| 5 | `pay_aoUARR5cAjlTCG` | `datasets/A20_B75_Cmax` | 03-26 11:10 | 03-29 11:00 |
| 6 | `pay_z3ScsKAKvjsOTt` | `datasets/A40_B100_Cmax` | 03-29 12:49 | 03-31 11:00 |
| 7 | `pay_072pCEtezYTRYT` | `datasets/A40_B100_Crandom` | 03-28 22:07 | 03-30 11:00 |
| 8 | `pay_shWVVWoIvcfAxX` | `datasets/A40_B100_Crandom` | 03-28 21:52 | 03-30 11:00 |
| 9 | `pay_53oRFUzJKOxhkz` | `datasets/A40_B50_Cmax` | 03-25 15:23 | 03-29 11:00 |
| 10 | `pay_JqWV6FiTif6FUi` | `datasets/A40_B50_Cmax` | 03-29 06:02 | 03-30 11:00 |
| 11 | `pay_rFqN9TWx3htxUC` | `datasets/A40_B50_Cmax` | 03-24 20:56 | 03-25 11:00 |
| 12 | `pay_FESJfq3yqo6Zwy` | `datasets_v2/A20_B75_Cmax` | 03-28 00:32 | 03-30 11:00 |
| 13 | `pay_IbSHVAG7iKV9Ax` | `datasets_v2/A20_B75_Cmax` | 03-30 12:02 | 04-01 11:00 |
| 14 | `pay_Ko1VrYFQKNauQn` | `datasets_v2/A20_B75_Cmax` | 03-27 09:27 | 03-30 11:00 |
| 15 | `pay_b73cZJFKWxYAoF` | `datasets_v2/A40_B100_Cfifo` | 03-29 02:23 | 03-30 11:00 |
| 16 | `pay_BPvO81IRr8QggD` | `datasets_v2/A40_B100_Cmax` | 03-26 10:08 | 03-30 11:00 |
| 17 | `pay_XJladnbolDIAVn` | `datasets_v2/A40_B100_Cmax` | 03-26 17:57 | 03-30 11:00 |
| 18 | `pay_pGnyvFqAYVaR2n` | `datasets_v2/A40_B100_Crandom` | 03-27 15:38 | 03-30 11:00 |
| 19 | `pay_2JyMYPlpq5LwT8` | `datasets_v2/A40_B50_Cmax` | 03-28 13:37 | 03-30 11:00 |
| 20 | `pay_e3Z4Giaefjqi9q` | `datasets_v2/A60_B100_Cmax` | 03-26 02:09 | 03-29 11:00 |
| 21 | `pay_k9iSklK3h1GufW` | `datasets_v2/A60_B100_Cmax` | 03-29 04:36 | 03-30 11:00 |

### 2.3 Neither precedence nor derivation — it is TEMPORAL

The reason is not "simply wrong": at export time these rows genuinely *are*
on hold. The reason is wrong *as at the horizon*, which is the only instant
the question is being asked about. Reordering the branches fixes nothing;
both branches are reading the wrong clock.

`disputes.json` carries `opened_at`, so "the hold had not begun at the
horizon" **is** derivable from merchant-visible data. Applying it moves all
21 to `not_yet_eligible`, correctly.

The converse is **not** derivable. `disputes.json` carries no `hold_until`,
so "the hold was released before the horizon" cannot be computed. §3b below
is exactly that case, and it stays wrong under any correction.

### 2.4 Simultaneously-true reasons: yes, and the count is large

Under the corrected temporal test, **142 rows** are both held at the horizon
*and* were previously labelled `rolled_forward`; **16** are both held and not
yet eligible. On the frozen precedence order (`not_captured` → `netted_out` →
`on_hold` → `not_yet_eligible` → `rolled_forward`) a scalar reason silently
discards the others.

**Finding, not implemented:** the outcome should carry a reason **list** with
the reported reason marked as primary. A held-and-not-yet-eligible row has two
different close conditions and two different owners — disputes ops and nobody
respectively — and a scalar cannot express that. This is reported for Part 2
to decide; it is not built here.

---

## 3. The 14 `netted_out` and 1 `not_yet_eligible` wrong reasons

### 3a — the 14, two sub-shapes, both the Task 1 mechanism

**Shape 1, over-refund (11 rows, 4 payments).** Identical to Task 1: refund #1
equals gross exactly and precedes eligibility, refund #2 is later and extra.
Truth calls the payment `not_yet_eligible_at_horizon` and each refund
`debit_deferred_past_horizon`. Affected payments: `pay_BDWg5QRepEvdZl`
(`datasets/A20_B100_Crandom0`), `pay_8CLmmfco9UHwdX`
(`datasets/A20_B75_Cmax`), `pay_eDcLBuuM3DJB1S` (`datasets/A40_B50_Cmax`),
plus refunds `rfnd_Z5aBjBpfDVILP4` (`datasets/A40_B100_Cfifo`) and
`rfnd_cWn0R0yFZv8aw7` (`datasets_v2/A20_B100_Cmax`).

**Shape 2, near-full aggregate after eligibility (3 rows, 1 payment).**
`pay_EkGSHCM91DOiUH` in `datasets_v2/A20_B50_Cmax`, amount 2,014,900, with two
refunds of 1,007,400 each = **2,014,800 — short of gross by exactly 100 paise
(₹1)** — and *both* created after `eligible_at`. The resolver's test
`2,014,800 >= 1,967,348` passes on the fee-net comparison alone. This is the
cleanest possible demonstration of divergence #2: a ₹1-short partial refund
reads as a full refund because it is being compared against a number reduced
by a ₹475 fee.

All 14 clear under the corrected predicate.

### 3b — the 1, and it is the one that does not clear

| row | dataset | claimed | truth | `on_hold` column | dispute |
|---|---|---|---|---|---|
| `pay_KlUO8AoQQAWwxF` | `datasets/A20_B50_Cmax` | `not_yet_eligible` | `on_hold_dispute` | **False** | `disp_Fvn9e1jV4sOSJ2` |

The mirror image of the 21. The hold *was* live at the horizon and has since
been released, so the static column reads `False`. Since `hold_until` is not
in `disputes.json`, no correction available to the resolver recovers this.

**Reported as a contradiction, not resolved here:** the recon feed cannot
answer the question `SETTLEMENT_SPEC.md` §3 makes load-bearing. The resolver
is being asked for a state at a past instant from a file that records only the
present.

---

## 4. Can `ProvenUnmatched` be gated at zero?

### 4.1 Per-reason verdict, corrected predicates, full enumeration

| reason (corrected) | right | wrong reason | **settled** | total | zero-tolerance? |
|---|---:|---:|---:|---:|---|
| `failed_at_gateway` | 215 | 0 | **0** | 215 | **YES** |
| `netted_out` | 484 | 0 | **0** | 484 | **YES, once fixed** |
| `not_yet_eligible` | 952 | 0 | **0** | 952 | YES, but see 4.2 |
| `dispute_held` | 271 | 10 | **64** | 345 | **NO** |

`failed_at_gateway` reads `credit == 0` — a payment never captured never
became money. Entailed.

`netted_out` after transcription is exact: payment and refunds annihilate and
neither leg ever pays out. Entailed.

`not_yet_eligible` is entailed **by a margin**, and the margin is provable
rather than lucky. The resolver's horizon is the last bank `value_date`; the
true horizon is the last batch `formed_at`, which is always earlier by the
posting lag (measured: 0.29 to 2.29 days). Testing `eligible_at > last bank
value_date` is therefore *strictly stronger* than testing against the true
horizon, so it can produce misses but never a false positive. 0 counterexamples
in 952 rows is a consequence, not a coincidence.

`dispute_held` fails with 64 counterexamples, and the breakdown says exactly
why:

| phase | status | unsettled | **settled** | safe? |
|---|---|---:|---:|---|
| fraud | `under_review` | 104 | **0** | yes |
| retrieval | `under_review` | 95 | **0** | yes |
| fraud | `won` | 43 | **19** | no |
| retrieval | `won` | 39 | **14** | no |
| chargeback | `lost` | 0 | **31** | **no — 100% settled** |

This maps exactly onto `SETTLEMENT_SPEC.md` §6.1. `retrieval` and `fraud`
*withhold* funds; `chargeback` *claws back after settlement*. Every one of the
31 lost chargebacks settled and was then reversed by a debit adjustment.
Calling a clawed-back row "correctly unmatched" is not a near-miss, it is the
wrong category.

Narrowing to `status == under_review` gives 199 rows and 0 counterexamples.
But that rule still reads a *current* status against a *past* horizon, which
is the defect §2.3 identifies. It is safe on this corpus; it is not entailed.

### 4.2 Where the reasons that cannot support it should go

Do not widen `ProvenUnmatched` to keep the taxonomy tidy.

| reason | destination | why |
|---|---|---|
| `failed_at_gateway` | `ProvenUnmatched` | never became money; permanent |
| `netted_out` (corrected) | `ProvenUnmatched` | both legs annihilate; permanent |
| `not_yet_eligible` | `OpenBreak / timing_difference` | provable **for this window only**; the row settles later. This is the textbook deposit-in-transit case and industry practice carries it forward with an age rather than closing it |
| `dispute_held`, `under_review` | `OpenBreak / unexpected_change` | hold is live; asserts nothing about the outcome |
| `dispute_held`, `won` | `OpenBreak / unexpected_change` | hold released — the hold is no longer why it is unmatched |
| `dispute_held`, `lost` (chargeback) | `OpenBreak / unexpected_change` | the row **did** settle; a clawback is a later debit, not a non-settlement |

`not_yet_eligible` is the interesting call. It *is* provable, so it could be
gated. It goes to `OpenBreak` anyway because `ProvenUnmatched` should mean
"no bank credit exists, ever", and a not-yet-eligible row's bank credit exists
next Tuesday. Gating a temporary state as a permanent proof is how the
distinction rots. It should carry a `provable_within_window: true` flag so the
strength of the evidence is not lost.

### 4.3 COMMITTED PREDICTION — written before Part 2 runs

Assumes Part 2 changes only the unmatched classification, leaving assignment
and consumption untouched, so the population stays 4,994.

| bucket | predicted rows | predicted G9 failures |
|---|---:|---:|
| `ProvenUnmatched / failed_at_gateway` | **215** | 0 |
| `ProvenUnmatched / netted_out` | **484** | 0 |
| **`ProvenUnmatched` total** | **699** | **0** |
| `OpenBreak / timing_difference` | 952 | n/a |
| `OpenBreak / unexpected_change` (hold live) | 199 | n/a |
| `OpenBreak / unexpected_change` (hold resolved) | 146 | n/a |
| `OpenBreak / upstream_unresolved` | 2,405 | n/a |
| `OpenBreak / unexplained` | 593 | n/a |
| **`OpenBreak` total** | **4,295** | n/a |
| population | 4,994 | |

**G9 failures on the first run: 0.** If `netted_out` ships without the
transcription fix, the prediction is **8**. If `dispute_held` is admitted to
`ProvenUnmatched` in any form, the prediction is **64**.

`OpenBreak / unexplained` at 593 is a real, reported category with 0 settled
rows. It is not a defect to be optimised away; it is the honest count of rows
whose absence from the bank the resolver cannot explain.

### 4.4 The honest guarantee sentence

> **`ProvenUnmatched` asserts that the merchant-visible ledger alone entails
> that this row's money never reached the bank — because it was never captured,
> or because it and its refunds annihilate to zero before it ever became
> eligible — and it makes no claim about any row whose settlement is merely
> deferred, withheld, or unknown.**

Weaker than "the ledger entails no bank credit exists", deliberately. It names
the two mechanisms it can actually discharge rather than defining an
unreachable ideal, following the precedent `RESOLVER_CONTRACT.md` §3.3 sets
for `Verified`.

---

## 5. `OpenBreak` clustering

### 5.1 The measurement

Over the 3,122 rows currently in the residual branch:

| | value |
|---|---|
| rows with a traceable causing bank line | **2,461** |
| distinct `(dataset, bank line)` causes | **83** |
| rows per cause — mean / median / min / max | **29.7 / 27 / 1 / 90** |
| rows with no causing line | 661 |

**2,461 flat queue items collapse to 83.** A 30× reduction, and the reduction
is the difference between a queue nobody reads and one an operator works
through in an afternoon.

Largest causes:

| dataset | line | outcome | rows |
|---|---:|---|---:|
| `datasets/A60_B100_Cmax` | 18 | `AttestationDiscrepancy` | 90 |
| `datasets_v2/A60_B100_Cmax` | 12 | `AttestationDiscrepancy` | 70 |
| `datasets/A60_B100_Cmax` | 4 | `AttestationDiscrepancy` | 66 |
| `datasets_v2/A60_B100_Cmax` | 6 | `AttestationDiscrepancy` | 65 |
| `datasets_v2/A40_B100_Crandom` | 1 | `AttestationDiscrepancy` | 59 |
| `datasets/A40_Bnone_Cmax` | 17 | `Unresolved` | 53 |

### 5.2 Variant B clusters the same way

| family | causes | rows | mean rows/cause | causing outcomes |
|---|---:|---:|---:|---|
| attested (28 datasets) | 60 | 1,716 | 28.6 | `AttestationDiscrepancy` 1,716 |
| absence (2 datasets) | 23 | 745 | 32.4 | `Unresolved` 689, `AttestationDiscrepancy` 32, `Ambiguous` 24 |

Clustering is slightly *tighter* at the absence points, not looser.

### 5.3 Every row has a cause — and the 661 without one are not a defect

The 661 rows with no causing bank line are exactly the rows that genuinely
never settled and were mislabelled with a residual reason. They have no cause
because there is nothing upstream to blame; they belong in
`ProvenUnmatched` or in a non-upstream `OpenBreak` reason, and the corrected
predicates in §4 move them there. **No row is unaccounted for.**

### 5.4 The cause field — and a defect that blocks it

Recommended shape:

```
OpenBreak.caused_by  : BankLineRef | None    # the line whose outcome blocks this row
OpenBreak.close_when : str                   # "bank line 18's attestation is resolved"
```

**Blocking defect, measured.** The resolver cannot currently name the cause
for most of these rows, because `_reversed_credit` constructs its
`AttestationDiscrepancy` with an empty `attested_row_ids`:

| `AttestationDiscrepancy` kind | count | names its rows |
|---|---:|---:|
| `claimed_credit_not_on_statement` | 22 | 22 |
| `temporal_impossibility` | 10 | 10 |
| **`credit_reversed`** | **30** | **0** |

Measured coverage of a cause pointer built from `attested_row_ids` today:
**50%** on `datasets/A10_B100_Cmax`, **18%** on `datasets_v2/A20_B100_Cmax`.
The `credit_reversed` lines are both the most numerous kind and the ones
dragging the most rows.

The fix is available and small — the settlement report names the rows for the
reversed settlement — but it is a change to `resolver/resolve.py` and belongs
to Part 2, not here.

At the absence points no attestation exists at all, so the pointer must
degrade to "was in the candidate pool of these `Unresolved` lines", which is
many-to-one and weaker. Part 2 should treat the absence-point cause pointer as
a distinct, weaker construct rather than pretend it is the same field.

### 5.5 The taxonomy needs a sixth reason

These rows are none of the standard five. They are not `missing_source` — the
source is present and legible. Not `timing_difference` — they are inside the
window. Not `mapping_issue` — they map fine. Not `unexpected_change` — nothing
about the row changed. Not `true_error` — no error has been established.

Their batch membership is unknown **because an upstream finding about a
different object is unresolved.**

> **`upstream_unresolved`** — this row's disposition depends on a bank line
> whose own outcome is not settled. Owner: whoever owns the causing finding,
> not whoever owns the row. **Closes when the causing line's outcome becomes
> `Verified` or `ProvenUnmatched`** — at which point every row clustered under
> it is re-evaluated together, not individually.

Predicted population: **2,405 rows under ~83 causes.**

Forcing these into `true_error` would assert an error nobody has demonstrated;
forcing them into `unexplained` would hide the one thing actually known about
them, which is precisely *why* they are open. Either move recreates
`ROLLED_FORWARD` under a new name.

---

## 6. Contradictions reported, not resolved

1. **`SETTLEMENT_SPEC.md` §3 vs the recon feed.** The spec makes hold state at
   the settlement horizon load-bearing. The recon feed publishes only a
   current-state `on_hold` boolean and `disputes.json` has no `hold_until`.
   One direction (hold began after the horizon) is recoverable; the other
   (hold released before the horizon) is not. 202 of 540 disputed rows are
   affected.
2. **`RESOLVER_CONTRACT.md` §4.6 vs `types.py:529`.** §4.6 requires every
   `UnmatchedReason` to be derived. `ROLLED_FORWARD` is defined in the same
   file as `"eligible, not selected"` — a residual by construction. The
   contract specifies the defect Part 1 measured.
3. **The two horizons.** The resolver's horizon (last bank `value_date`) and
   the oracle's (last batch `formed_at`) differ by 0.29–2.29 days across the
   corpus. For `not_yet_eligible` the difference is safe in one direction
   (§4.1). It is not obviously safe for any future reason that tests the
   horizon in the other direction, and no test currently guards that.

---

## 7. Addendum — `attested_row_ids` is overloaded, not merely unpopulated

Asked before Part 2: is `credit_reversed`'s empty row set a local omission, or
a gap in the discrepancy record? **It is a gap, and it affects three of the
three `AttestationDiscrepancy` kinds the corpus produces.**

| kind | n | rows named | rows in the true batches | meaning at that call site |
|---|---:|---:|---:|---|
| `claimed_credit_not_on_statement` | 22 | 688 | 688 | the **whole attestation** |
| `temporal_impossibility` | 10 | **13** | **294** | only the **offending subset** |
| `credit_reversed` | 30 | **0** | 783 | **nothing** |

Real cause-pointer coverage across all 62 discrepancies is **701 of 1,765
rows (39.7%)**, not the 50%/18% sampled in §5.4.

`temporal_impossibility` is the sharpest case: 13 rows named out of 294 in the
affected batches (4.4%). As a contradiction record that is *correct* — those
13 rows are the ones that cannot have been in the batch. As a cause pointer it
is useless, because the other 281 rows are equally blocked by the same
unresolved finding.

Three construction paths, three semantics:

* `resolve.py:421, 435` — `rows=tuple(claimed)`, the full attested set;
* `resolve.py:457, 470, 542` — `rows=tuple(impossible)` / `tuple(double)`,
  only the rows implicated in the contradiction;
* `resolve.py:412` — `CLAIMED_CREDIT_NOT_ON_STATEMENT` with **no `rows=`**
  at all (unreached in this corpus; all 22 come from line 421);
* `resolve.py:369` — `_reversed_credit` bypasses the `_discrepancy` helper
  entirely and populates neither `attested_row_ids` nor `Contradiction.row_ids`.

`RESOLVER_CONTRACT.md` §4.2 never defines `attested_row_ids`. An undefined
field acquired three meanings, which is what an undefined field does.

**Two questions were being answered by one field:**

1. *Which rows are implicated in the contradiction?* — the contradiction
   record. `Contradiction.row_ids` already exists for exactly this and is
   currently set to the same value as `attested_row_ids` at every site.
2. *Which rows did the PSP attest to this line?* — what the `OpenBreak` cause
   pointer needs, and what nothing currently answers reliably.

Patching `_reversed_credit` alone would raise coverage to roughly 83% and
leave `temporal_impossibility` silently under-pointing. The separation is the
fix; the type system already provides both fields.

This is recorded as a **finding**, not applied here.
