# DECISIONS.md — the matching cascade

Every non-obvious choice, with the alternative it beat and the evidence.
"I used X" is not a reason. Where a rejection is backed by a measurement, the
measurement is quoted; where it is a judgement, it is labelled as one.

Phase 1 (the frozen dataset) is unchanged by this work. Nothing under
`engine/data/`, `engine/ground_truth/`, `engine/simulator.py`,
`engine/generator.py` or `DATASET_HASHES.txt` was touched.

---

## 1. Stage 3 withholds the settlement columns from its own input

**Decision.** The reconstructor never sees `settlement_id`, `settled`,
`settled_at` or `settlement_utr`. It is handed a target amount and a candidate
pool and returns every subset that nets to the target.

**Rejected: group rows by `settlement_id` and check the total.** It is one line
of code and it is what the recon file invites. It also makes ambiguity
**structurally invisible** — every batch resolves to exactly one grouping,
including the two that provably admit more than one. Measured: grouping by
`settlement_id` reports 12/12 determinate. The reconstructor reports 3
ambiguous, and the ground-truth key confirms 2 of them were planted.

Those four fields are one assertion written in four places. Withholding one and
reading another would be self-deception, so all four go.

**Why this matters beyond the test set.** `settlement_id` is Razorpay's
assertion; the bank statement is the source of truth. A merchant reconciling a
second gateway, a historical period, or a bank feed alone has no
`settlement_id` to lean on — and when the assertion is *wrong*, only an
independent reconstruction can notice.

---

## 2. The attestation IS used for pool advancement — and why that is not circular

**Decision.** Rows an *earlier* bank credit already paid out are removed from
later pools, and the recon file's `settlement_id` is how the engine knows which
those are. It bounds which rows are candidates. It never chooses among them.

**The distinction is load-bearing.** The enumerator is blind to which candidate
the attestation names, which is why it can and does disagree with the file it
was given (§8). An auditor genuinely knows last week's settlement is banked
fact; that is not privileged information.

**Rejected: fully blind chronological reconstruction**, where the pool advances
only on the solver's own determinate answers. Measured, and it collapses: an
ambiguous batch consumes only the rows common to every candidate, the contested
remainder pollutes the next pool, which becomes ambiguous in turn. Pools grew
`5 → 23 → 30 → 56 → 71 → 86 → 95 → 106 → 123 → 133 → 154 → 159`, every batch
from the third onward hit the enumeration cap, and the engine reported
essentially nothing. A cascade failure, not a finding.

**Rejected: global set-partitioning ILP.** Model the whole statement at once —
each row assigned to at most one bank line, each line's net pinned to its
amount. Strictly the strongest formulation and it removes the pollution problem
entirely. Measured: 1,347 booleans, **no solution in 60 seconds** (status
UNKNOWN). Recorded here rather than dropped, because it is the right answer if
someone wants to spend the engineering: the correct next step is a
column-generation or set-cover decomposition, not a bigger time limit.

---

## 3. CP-SAT, not CBC via PuLP

**Decision.** OR-Tools CP-SAT with native solution enumeration.

**Rejected: PuLP + CBC with no-good cuts.** Built first, and it works — it is
just unusable. Measured on this ledger:

| pool | CBC + no-good cuts | CP-SAT |
|---:|---:|---:|
| 5 rows | 0.05s | 0.006s |
| 23 rows | **38.48s** | 0.236s |

The cost is not finding solutions, it is *proving there are no more*.
Subset-sum has a famously weak LP relaxation, so after the last real solution
CBC must exhaust the branch tree to prove infeasibility, and each accumulated
no-good cut makes the next round-trip slower. CP-SAT enumerates solutions
natively through a callback and is built for exactly this.

PuLP was removed from the dependency set rather than left in as a dead
alternative.

---

## 4. The objective is "defer as few debits as possible"

**Decision.** Maximise the number of pending debits *applied*, then enumerate
every solution achieving that optimum. The payment side is entirely
unconstrained.

**Why an objective at all.** A refund or adjustment is *applied*, not selected —
a merchant does not choose which refunds to pay back this week. But spec §1.4
lets a batch **defer** debits when the payout would otherwise go negative, and
this ledger does exactly that twice (batch 0 defers 1 debit; batch 11 defers 5).
So "all pending debits apply" is false, and "debits are free" is too weak.
Deferral is permitted exactly when arithmetic forces it.

**Rejected: leave the debit side free too.** Measured — it inflates three
determinate batches into ambiguity by inventing debit combinations no
settlement process could produce:

| bank line | debits free | min-deferral | ground truth |
|---|---:|---:|:-:|
| 1 | 3 candidates | 1 | determinate |
| 8 | 3 candidates | 1 | determinate |
| 9 | 7 candidates | 2 | **ambiguous** |

**Rejected: treat all pending debits as mandatory.** Simplest, and it produces
*no solution at all* for batches 0 and 11, where deferral actually happened.

**This constrains only the debit side.** Nothing prefers larger payment
subsets, earlier captures, or more rows — so the reconstruction stays
**selection-rule-agnostic**. The same code returns the same answers if the
ledger had been formed FIFO. Eligibility (T+2) bounds the candidate pool only;
it never chooses among candidates.

---

## 5. Ambiguity is a type, not a flag

**Decision.** `Resolution = Determinate | Ambiguous | Unresolved`, and
`Ambiguous` **has no `decomposition` attribute at all**.

**Rejected: `Determinate(rows, is_ambiguous=True)`.** A boolean is a field
someone can forget to read, and the failure is silent and plausible-looking.
With no attribute to access, a caller wanting an assignment must first narrow
the union — the wrong answer is unrepresentable rather than discouraged.

Supporting rules, each with a reason:

- **`resolve_from_candidates` is the only constructor.** It enumerates first
  and decides confidence from the count. There is no pick-then-check path.
- **One candidate + truncation ⇒ `Unresolved`, not `Determinate`.** Truncation
  means enumeration stopped early, so "one found" is not "one exists".
  Reporting determinate would assert something never checked.
- **`certain_rows` is empty when truncated.** An unseen candidate could drop
  any of them, so optimism is unfounded.
- **`Determinate.__post_init__` raises `BalanceViolation`.** The postcondition
  is enforced at construction, so a non-closing determinate cannot exist even
  transiently. A violation is a bug to surface loudly — deliberately *not* an
  exception type Stage 4 can route away, because routing it would hide a wrong
  answer behind a plausible-looking queue.

---

## 6. Enumeration cap of 32, and what truncation means

**Decision.** At most 32 tying decompositions per bank credit; beyond that the
batch is marked `truncated` and its candidate list is explicitly a **sample**.

A batch with more than 32 tying subsets is **more** ambiguous, not less, so
truncation never upgrades confidence. Measured worst case on this ledger: 2
candidates, and `test_no_enumeration_was_truncated_on_this_ledger` asserts the
cap was never reached — so 32 is headroom, not a binding constraint whose
effects are being hidden.

---

## 7. Tolerance scales per row, and the batch identity has none

**Decision.** Two different tolerances, because they answer different questions.

- **Batch balance identity: tolerance 0.** `Σcredit − Σdebit == bank_amount`
  exactly. Batch arithmetic is integer paise throughout; there is no rounding
  step inside a batch, so any residual is a bug. Asserted at 0 in
  `test_balance_identity_holds_on_every_determinate_resolution`.
- **Aggregate comparisons: 1 paise per row.** The only legitimate drift is
  ±1 paise of ceiling-rounding per fee-bearing row, so the budget must scale
  with how many rows the amount aggregates.

**Rejected: a flat ±₹1 window.** Explicitly warned against and correctly so —
across a 20-payment batch a ±₹1 window spans a range wide enough to admit a
wrong subset. Scaling by row count keeps the budget proportional to the actual
source of error.

Where the ±1 paise residuals really live is the GST leg (§10), not the batch.

---

## 8. One extra ambiguous batch is reported, and it is not a false positive

The engine flags **3** batches ambiguous; the key marks **2**. The third,
`setl_nXePRBtWmHMwcp`, is real.

The key records ambiguity as the *simulator* defined it: ties among subsets
achieving the maximum sum under the live-balance cap. The engine asks a
different and stricter question, because it is the only question a
reconstructor can ask — *given only the bank credit and the pool available that
day, is there more than one subset that nets to it?* For this batch there are
two, and both are enumerated. Naming one would assert something unknowable.

This is a **conservative disagreement**, and it costs match rate (7 rows
declined). It is reported as a disagreement rather than smoothed away, because
the alternative — tuning the solver until it agrees with the key — is exactly
what the freeze exists to prevent.

`test_the_true_decomposition_is_always_among_the_candidates` asserts the true
answer is in the enumerated set on **every** batch, ambiguous or not. The
engine is never wrong; on three batches it declines to be certain.

---

## 9. Blocking is generous, the gate is strict

**Decision.** ERP candidate *generation* uses a wide window (±2% amount, ±3
days). ERP candidate *acceptance* requires a shared identifier.

**Why the asymmetry.** They are different jobs. A pair blocking never proposes
can never be examined, so "we found nothing" and "we looked and refused" become
indistinguishable — and they are very different claims about an engine. With
the wide window, blocking proposes 1 pair and the gate refuses it; Hungarian
proposes 6 and refuses all 6. Those refusals are counted in the report.

**The gate is "shared identifier", not "high similarity".** Amount and date are
not evidence of identity, and this dataset contains 4 deliberate same-amount
same-day decoy pairs specifically to catch a matcher that thinks otherwise.

**Consequence, accepted deliberately:** the 14 payments with no ERP order and
the 6 orphan invoices stay unmatched. They are real control failures. A
plausible-but-wrong partner would close a genuine finding, and false positives
cost more here than a lower match rate.

**Fuzzy algorithm: `rapidfuzz.fuzz.token_set_ratio`** for narration. Narration
corruption in this dataset is truncation and masking, which preserves token
content while destroying order and length — `token_set_ratio` is insensitive to
both. **Rejected: plain `ratio`**, which penalises the length change caused by
truncation and would score a merely-truncated narration as a mismatch. Narration
is scored and reported but never *decides* a match; the (amount, date) fallback
does.

---

## 10. Tax leg: the supplier is identified, not assumed

**Decision.** Nothing in the data labels which GSTR-2B supplier is the payment
gateway. It is identified as the supplier whose invoice taxable values
reconcile to the fee actually deducted, month by month — the way an accountant
would. Verified against the key by
`test_the_supplier_gstin_is_identified_not_assumed`.

**Rejected: hardcode the GSTIN, or take the most frequent supplier.** The first
is untransferable to any other merchant's file. The second is wrong here — the
gateway has 2 invoices against 18 from other vendors.

**Monthly, not per settlement.** Razorpay consolidates fees into one tax
invoice per month, so one 2B line ties back to N settlements.

**Rounding residuals are reported, not reconciled away.** A consolidated
invoice computes GST once on the monthly aggregate; the ledger accrues
ceiling-rounded tax per transaction. Measured: −10 paise (June) and −30 paise
(August), both inside the per-row tolerance. Forcing either side to match would
destroy the finding.

**Fee charged with no GST is excluded from taxable value**, not netted into it —
there is no input tax on those rows to claim. Surfaced as its own line.

**One methodological difference from the key, stated openly.** For the
absent-from-2B period the engine reports ITC at risk of **143,434 paise** where
the key says **143,400**. The invoice does not exist, so the engine cannot read
its tax and uses accrued tax instead — a 34-paise difference and the best
estimate available without the document. All three grounds and periods agree
exactly.

**Rule 37A is computed, never read.** GSTR-2B reports
`itc_availability: Yes` for that invoice. The exposure is invisible in the
return and only exists if you check the supplier's filing status against the
credit already taken. That is the most interesting of the three grounds and the
reason the extra 2B columns are carried.

---

## 11. The LLM narrates and never matches

**Decision.** `type` and `owner` — the fields that determine what *happens* to a
row — are assigned by deterministic rules. The model is handed an
already-decided classification and asked to phrase it. Its output goes to
`narrative`, which nothing downstream reads.

**Rejected: LLM-assisted matching, even as a tie-breaker on ambiguous batches.**
It is the obvious demo and it is wrong. A model asked to break a tie between two
arithmetically identical subsets has no information the solver lacks — it would
be guessing with a confident tone, on precisely the cases where the correct
answer is "this cannot be determined". It would also make the pipeline
non-deterministic exactly where auditability matters most.

**Default is the deterministic explainer.** Every test and every eval run uses
it, so output is byte-identical run to run. Live Claude is opt-in via `--llm
claude`, and falls back to templates on any failure — an unavailable model must
never change what the pipeline decides.
`test_narration_is_the_only_field_an_explainer_can_touch` runs the whole
cascade with a hostile explainer that returns "WRONG, MATCH IT TO SOMETHING
ELSE" for every row, and asserts the matching output is unchanged.

**Confidence is a stated scale, not a vibe:**

| value | meaning |
|---:|---|
| 1.00 | read directly off an explicit field (`on_hold`, `fee is null`) |
| 0.90 | derived by arithmetic over the ledger (refunds cancel a payment) |
| 0.75 | inferred from an **absence** (no ERP order exists) |

Absence is weaker evidence than presence because it cannot distinguish
"missing" from "never existed".

---

## 12. What "match rate" means — and the three buckets

This was a definitional decision, not a default, and it was settled before any
eval code was written.

**Decision.** 37 of 240 rows correctly have no bank credit — netted out by a
full refund, rolled forward, dispute-held, deferred, or failed at the gateway.
Matching one would be a **false positive**. They are excluded from the
denominator and reported as their own bucket, itemised by reason:

    match rate = correctly placed / rows that truly settled = 196 / 203 = 96.55%

**Rejected: denominator of all 240 rows.** Caps the score at 84.6% regardless
of engine quality and makes the headline mostly a function of how many pending
rows the period happened to contain.

**Rejected: count correct classification as a match.** Gives the highest number
and conflates "I found its bank credit" with "I explained why it has none".

The row accounting is **disjoint and asserted to partition all 240 rows**
(`test_row_accounting_partitions_every_row`). ERP and GST findings are a
*separate axis* — a payment can be correctly matched to its bank credit and
still have no ERP order — so they are not counted in it. Mixing the two axes is
how a row gets counted twice and how a match rate stops meaning anything.

**Precision and recall are computed over determinate batches only**, and
**ambiguity handling is scored separately**. An ambiguous batch has no single
right answer to be precise about. Crediting a match because the truth is
somewhere in the candidate list would reward enumerating more candidates — a
solver returning all 2ⁿ subsets would score perfectly.

**The 7 declined rows count against the match rate.** They are the difference
between 96.55% and 100%, and they are the right answer.

---

## 13. Zero-net groups are removed from the pool

**Decision.** A payment fully refunded before it could settle contributes 0 to
every sum, so it can be added to or removed from **any** decomposition without
changing the total — making every bank credit ambiguous for a reason that has
nothing to do with settlement. 7 such groups (14 rows) are detected from the
ledger alone and excluded from candidate pools, then reported as
`netted_out_by_full_refund`.

**Rejected: leave them in and report the resulting ambiguity.** Technically
honest and practically useless: it is an artefact of arithmetic, not a finding,
and it would drown the two real ambiguities.

---

## 14. Determinism

`num_workers = 1` on every CP-SAT solve. Multi-threaded search returns
whichever solution a race produced first, which makes enumeration order — and
therefore any truncated candidate list — vary run to run. The cost is
irrelevant at these pool sizes and the property is worth more than the speed.

Three consecutive runs produce byte-identical output, asserted over a SHA-256
fingerprint of every assignment, resolution, candidate list and exception.

---

## 15. Runtime

Full cascade: **~1.4 s**. Slowest single bank credit: `bank[3]` at 1.28 s over a
27-row pool. Well inside the "few seconds per batch" budget, so no approximate
method was substituted.

`SOLVER_TIME_LIMIT_SECONDS = 30` is a reported ceiling, not a silent fallback:
a breach sets `over_time_budget` on the reconstruction and appears in the eval
report. **This does not scale to a real merchant book** — see §2 on the global
formulation, and `SETTLEMENT_SPEC.md` §1.5 on why exact enumeration is the
wrong algorithm above a few dozen eligible rows. Stated as a boundary rather
than left to be discovered.

---

## 16. An audit finding that was rejected, and why

Recorded because **an audit finding with no recorded response reads worse than
one that was never raised.** This one was raised during Phase 1, examined, and
rejected on the merits.

**The finding.** An independent audit pass reported a table headed *"6 of 14
classes missing"* — that the generated dataset contained no rows for six of the
planted hard-case classes, and was therefore not exercising the cases the test
plan claimed.

**Why it was rejected.** The table was built against a **different class list
than the one the brief defines.** The auditor enumerated fourteen classes of
its own construction — plausible reconciliation scenarios, but not this
project's numbered list — and then reported the ones it could not find in
`ground_truth.json` as absent. The six "missing" entries were cases the brief
never planted and never claimed to plant. Measured against the actual list, the
count of absent classes was zero, which is what `GENERATION_REPORT.md`'s "Class
coverage" table reports and what `engine/tests/test_classes.py` asserts per
class with an explicit tolerance band.

**What would have changed the decision.** A single class from *the brief's own
list* showing a zero count. That is a real defect and the test suite fails on
it — the assertion is per class, not on the total, precisely so a missing class
cannot be masked by an inflated neighbour.

**What was accepted from the same pass, and acted on.** The audit separately
observed that same-day same-amount payment pairs were rare enough that a
matcher keying on `(amount, date)` could score well without ever being caught.
That was correct and was a genuine gap: it became **`c15_same_day_same_amount_decoy`**,
8 rows, planted deliberately so that a matcher relying on amount-and-date as
identity is detected rather than rewarded. It is the reason the list is fifteen
classes and not fourteen, and the reason
`stage2_fuzzy._erp_gap_candidates` reports refusals rather than silence.

**The general rule this sets.** A finding is answered against the artefact's
own stated contract, not against a reviewer's reconstruction of what the
contract should have been. Where the reviewer's list is *better* than the
brief's — as it was on decoys — the brief changes. Where it is merely
*different*, the finding is recorded as rejected, with the reasoning, rather
than absorbed by quietly widening the claim.

---

## 17. Held-out validation: design and the seed-commitment protocol

**The problem.** Every number in §12–§15 was measured on data this project
built. That is not worthless — the ground-truth key is isolated, the solver
cannot read it (§1, `tests/test_isolation.py`), and `ROBUSTNESS.md` shows the
dataset was not seed-swept. But it is answerable in one sentence: *"the engine
was tuned against the only dataset it has ever seen."*

**Decision.** A second dataset, `holdout/`, generated by the **unmodified
frozen generator** at a **different seed** over a **non-overlapping period**,
scored with the **same metric definitions** (§12) and the **frozen solver**.

**The seed-commitment protocol, which is the part that makes it held-out.**
A held-out set is not a held-out set because it is new; it is held-out because
the experimenter could not have chosen it after seeing the result. So:

1. The seed is chosen and **committed to git in its own commit**, whose message
   states it is the held-out seed and that no data has been generated yet.
2. Only then is the data generated.
3. The engine is run **once**. The result is reported whatever it is.
4. The seed is **never reselected**, and no seed sweep is run.

Points 1 and 2 are the load-bearing ones and they are verifiable from
`git log`: the commit containing the seed precedes the commit containing the
data. Without that ordering the exercise is just another draw.

**Rejected: holding out a slice of the primary set.** Cheaper, and standard
practice in ML, but wrong here. The rows are not independent — they share
batches, and a batch is the unit the engine reconstructs. Splitting rows
across a train/test boundary would cut batches in half and measure something
the engine does not do.

**Rejected: regenerating the primary set at a new seed and comparing.** That
destroys the freeze, which is the single strongest integrity property this
repo has. Held-out data is NEW files in a NEW directory; nothing under
`engine/` is regenerated.

**The solver is frozen at `81c04e0` for the duration.** If the engine performs
worse on held-out data, that is the finding and it is reported as the headline.
Tuning the cascade until the held-out numbers improve would destroy the only
thing the held-out set is for, and is worse than not running one.
