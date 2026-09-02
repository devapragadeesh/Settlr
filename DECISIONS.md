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

---

## 18. Modelling a settlement reversal, and where it lives

**Decision.** `h01_settlement_reversal_resettled` exists **only in `holdout/`**,
never in `engine/`. The frozen set stays frozen; the unseen class is introduced
in new files in a new directory.

**Provenance is `synthesized_modelled` and this is not a hedge.** Razorpay
documents no reversal or failed-payout behaviour that this project could find,
and `SETTLEMENT_SPEC.md` §10 has always said so. Nothing about the mechanism is
claimed to be observed Razorpay behaviour. It is the standard bank/aggregator
mechanism: credit under UTR-A, NEFT return, debit referencing UTR-A,
re-settlement under UTR-B.

**Why it had to be a new bank-statement shape.** §10 originally listed
reversals as "genuinely absent" precisely because modelling one needs two
things the primary statement does not have: a **negative amount**, and a
**credit whose composition duplicates an earlier credit's**. Adding either to
`engine/data/` would have meant regenerating the frozen set — trading the
strongest integrity property in the repo for one extra class. The held-out
directory is what makes having both possible.

**Decision: the ledger rows re-point to settlement B.** `recon_combined.json`
is a current-state snapshot and B is the settlement that actually paid them.
The key retains A, marked `reversed_by`, because A genuinely occurred and was
genuinely reversed; `resettlement_of` points back, so the linkage is
recoverable in both directions.

**Rejected: leave the rows attesting UTR-A and add B as an unattested credit.**
It makes the re-settlement invisible to any consumer of the recon file, which
is not how a merchant sees it — and it would have made the engine's job
*easier*, which is the wrong direction for a test designed to find a gap.

**Rejected: express the reversal as a ledger adjustment row.** Cheap, and
wrong: a NEFT return is a bank-side event that the payment ledger does not
witness. Modelling it inside the ledger would have let Stage 1 join it and
would have tested nothing.

**Which batches may carry one** is constrained — not the last two, not the
blanked-UTR row, not an ambiguous batch, not one whose re-settlement crosses a
month boundary — and each exclusion is documented in `_eligible_for_reversal`
**with the direction of its bias**. The two substantive ones make the case
*cleaner and therefore easier*: excluding ambiguous batches keeps `h01`
attributable rather than confounded with `c07`, and excluding month-crossing
re-settlements keeps monthly fee accrual and `gstr2b.csv` untouched so the
reversal is not a tax finding in disguise. Both are stated rather than
presented as neutral, and the untested harder cases are named as untested.

---

## 19. What the held-out run found, and why the engine is not patched for it

**The result.** Match rate 96.55% → **73.11%**, precision 1.000 → **0.786**,
50 rows placed in the wrong batch. Full detail in
`holdout/HOLDOUT_RESULTS.md`.

**The finding, stated as the headline rather than buried.** On a settlement
reversal the engine does **not** decline. It places the affected rows into the
*original* credit A, with a closing arithmetic proof, at full confidence — and
the truth is that they belong to the re-settlement B. A confident wrong answer,
which is the worse of the two failure modes.

**Why it happens, mechanically.** `stage3_solver.run` walks bank lines in date
order and asks of each: *which pool rows net to this amount?* At credit A's
date the correct answer to **that question** is exactly those rows. They did
compose that credit; the credit did post. The engine is not hallucinating — it
is answering a question with no notion of revocation in it. Recognising the
reversal requires relating a **later** debit to an **earlier** credit, which is
state the cascade does not carry.

**The second-order cost is worse than the first.** Credit A resolves
`Determinate` and carries no attestation, so `run()` takes the `elif` branch
and **consumes** those rows. Credit B then reconstructs from a pool its own
rows are missing from. **One reversal damages two bank lines.** On `bank[9]`
that surfaced as an ambiguity with 29 candidates that did not contain the truth,
and it alone accounted for 9.4s of the 10.5s run.

**What the engine got right, and it is not nothing.** All three reversal debits
resolve `Unresolved` and reach the exception queue as `genuinely_unresolved`,
with the damaged credit-B lines — 5 bank lines against 0 on the primary set. The
queue does say *"I cannot explain these debits."* What it never says is
*"...therefore my earlier answer about credit A is void."* Zero balance-identity
violations: the engine is wrong about **which** rows, never about the sum.

**Attribution is total, and that is the other half of the finding.** All 50
mis-placed rows belong to a reversed batch; **zero** non-reversal rows were
harmed. Excluding reversal rows, the held-out set scores 95.68% with 0 placed
incorrectly, 0 missed, and the same 7 declined on proven ambiguity. Reported as
an explicitly labelled diagnostic — **the headline stays 73.11%**, because an
engine does not get to exclude the cases it failed.

**Decision: `matching/` is NOT modified.** The fix is not difficult — carry
reversal state, treat a debit referencing a prior UTR as revoking that credit,
and release its rows back to the pool. It is deliberately not written.

**Rejected: fix the cascade and re-run.** This is the one that matters. Tuning
a solver until the held-out numbers improve destroys the only thing a held-out
set is for, and the second run would no longer be held out. The engine is
frozen at `81c04e0` and the number stands. A repo that reports 73.11% with the
mechanism explained is worth more than one reporting 96% on a set it was
allowed to see twice.

**Rejected: regenerate the held-out set without reversals.** Same failure,
dressed as data cleaning.

**What a fix would have to be, recorded so the gap is bounded rather than
open-ended.** Reconciliation state is not derivable from one date-ordered pass:
a credit's resolution must remain revisable while any later line can revoke it.
That is a two-pass or event-sourced formulation, not a new stage bolted to the
end of a cascade — which is why it is a design change and not a patch, and why
doing it under time pressure in the phase that discovered the problem would be
the wrong order of operations.

---

## 20. The resolver contract is written and committed before the corpus exists

**Decision.** `resolver_contract/RESOLVER_CONTRACT.md` and `types.py` are
interface and semantics only — no algorithm, no solver, no matching logic —
and are committed in their own commit, before any corpus dataset is generated.
`git log` shows the ordering.

**Why the ordering is the point.** A corpus built before the contract gets
shaped to whatever the implementation happens to do; a contract written after
the corpus gets shaped to whatever the corpus happens to contain. Writing the
contract first is what stops the benchmark measuring its own author's
assumptions. This is the same argument §17 makes about the held-out seed, and
it is verifiable the same way.

**Rejected: define the outcomes as part of building the resolver.** Cheaper and
the normal order of work. It also means the vocabulary is chosen by whoever
knows what their code can already produce, which is precisely how
`Determinate` came to mean "unique among subsets maximising applied debits"
while being read as "this is the answer."

**Rejected: a confidence score in [0,1].** Makes every wrong answer a
threshold-tuning exercise and makes the KIND of claim invisible — 0.9 cannot
distinguish "two independent parties agree" from "one party asserted it and
the arithmetic is consistent with itself." A score can live inside an outcome;
it cannot replace one.

**Rejected: keep `Determinate` / `Ambiguous` / `Unresolved`.** They are a
taxonomy of the solver's epistemic state. They have no vocabulary for *the
record being wrong* — the most valuable thing a reconciliation engine can say —
and none for the difference between corroborated and arithmetically unique.

---

## 21. Independence is counted over PARTIES, and evidence declares what it attests to

**Decision.** `Evidence` carries `derived_from` (which source systems its
content came from) and a FIXED `attests_to` from a table the resolver cannot
override: `COMPOSITION`, `EXISTENCE`, `CONSEQUENCE`, `ROW_EXISTENCE`.
`SOURCE_PARTY` collapses source systems to parties, and only parties count.

**The measurement that forced it.** On the frozen set
`settlement_utr == str(settled_at) + settlement_id[-6:]` on 11 of 11 batches
and the narration embeds it on 9 of 12 lines. The settlement id and the bank
UTR look like two sources and are one. A rule counting *evidence kinds* would
have called that corroboration.

**And existence is not composition.** A bank reference says ₹99,329.23 arrived
on a date under a reference. It says nothing about which of 21 eligible rows
composed it. **A bank knows what it paid; it never knows what it paid *for*.**
Letting existence evidence corroborate a composition claim certifies a
composition on evidence that cannot bear on it. Same one level down for ERP: an
`order_id` proves a row is a real sale and carries zero batch-membership
information, because no ERP file contains a settlement reference.

**So `Verified` claims something weaker, stated precisely.** Not "the
composition is proven" — no party outside the PSP ever watches a batch form, so
that outcome could never occur. It claims: *one party made a composition claim,
that claim entailed a falsifiable prediction about an independent party's
records, and the prediction held.* It could have failed, and
`AttestationDiscrepancy` is what happens when it does.

**Rejected: require independent witness of composition.** Correct in principle,
empty in practice — every dataset would score zero `Verified`. Naming the limit
beats defining an unreachable ideal.

**Rejected: let the resolver declare what its evidence attests to.** Then the
oracle checks the resolver's rule against the resolver's own self-report, which
is a tautology. The resolver declares only `derived_from`, and §7 of the
contract has the oracle validate that against the corpus provenance graph.

**Consequence, accepted and measured rather than hidden:** corroboration is
only as strong as the prediction was discriminating. So
`Verified.rival_closure_count` is mandatory — the number of subsets closing to
the same amount under no objective — and `rival_closure_count = 0` is rejected
at construction because 0 means it was never measured. Decisiveness is
reported, not required: requiring it would make `Verified` unreachable on
exactly the large pools the corpus exists to explore, converting an honest
weakness into a hidden abstention.

---

## 22. `Reconstructed` requires cross-line exclusivity, not merely unique closure

**Decision.** An unattested reconstruction is only representable when the
subset closes uniquely under no objective **and** closes no other unexplained
credit in the window.

**Why uniqueness alone is not enough, measured.** At all three bank lines that
produced the 50 wrong rows, the pool admitted **exactly one** closing subset —
`OPTIMAL`, untruncated, no tie to miss (`investigation/DEFECT_REPORT.md` §1).
Per-credit uniqueness held perfectly and the answer was still wrong, because
those rows were the true composition of a *later* credit. **Uniqueness is a
per-credit predicate answering a cross-credit question.**

**Rejected: `Reconstructed` on unique closure alone.** This is remediation
option 5 in §6 of the defect report, already costed: 67.00% on the primary set
and 40.57% on held-out **with all 50 rows still wrong**. Adopting it would have
shipped the known failure with a warrant attached, making it look *more*
credible.

**Disclosed limit.** Cross-line exclusivity is necessary, not sufficient — a
credit that has not posted yet cannot be excluded against. §2 records that the
global formulation returned UNKNOWN at 60s on 1,347 booleans, so satisfying
this cheaply is open work. Named rather than discovered later.

---

## 23. Abstention is gated, on a subpopulation the corpus can prove is determined

**Decision.** `DeterminedInstance` = unique closure under a complete
objective-free enumeration, attestation present, attestation correct. On those,
`Unresolved` and `Ambiguous` are **failures**, gated at zero.

**The hole it closes.** Every other hard guarantee in the contract is a
soundness guarantee, and every soundness guarantee is satisfied by a resolver
that returns `Unresolved` to everything: no wrong `Verified`, no uncorroborated
warrant, no ambiguity missing its truth, no unwarranted assignment — all zero,
all vacuous. Worse, enumeration truncates first on the biggest pools, so **the
most adversarial cells of the corpus would produce the cleanest numbers in the
report.** A contract with only soundness gates is a certificate of abstention.

`DeterminedInstance.__post_init__` refuses construction from a capped
enumeration, so the subpopulation cannot be quietly widened to flatter a
resolver.

**Rejected: gate on overall coverage or match rate.** A coverage gate rewards
guessing — which is how a 1.000 precision that the defect report calls "a
property of the dataset and the tie-breaker" got reported as an engine
property. Gate soundness broadly, coverage **narrowly**. Both are needed;
neither is sufficient.

**Rejected: free-text `Unresolved` reasons.** They aggregate to nothing.
`no_subset_closes` and `enumeration_truncated` are different findings and the
second is the loophole; an enum forces both to be counted.

---

## 24. The bank becomes an independent source, enforced by a function signature

**Decision.** `corpus/generator/bank.py` takes a `Payout` carrying an amount
and an initiation timestamp and **nothing else** — no settlement id, no entity
ids, no `Batch`. It mints its own reference on its own counter with its own
gaps, posts on its own clock with a lag that crosses weekends, formats its own
narration (sometimes without the reference), interleaves foreign credits and
debits, and emits in its own order.

**The guarantee is the signature; the tests corroborate it.** If a field is not
on `Payout`, no bank-side artefact can encode it. Compare
`engine/generator.build_bank_statement(rng, batches, ...)`, which receives
`Batch` objects and writes `b.utr` into two columns.

**Where the line is.** *A bank field may correlate with a ledger field through
a modelled physical mechanism; it may not be computed from one.* Amount,
approximate date and the remitter's name are permitted and enumerated. The
amount **must** leak — it is the join evidence and the reason reconciliation is
possible at all.

**Rejected: hash the derived UTR (`sha256(settlement_id)[:12]`).** Still a
total function of ledger state. A solver that thinks to hash wins for free, and
a string-similarity test would pass while the leak persists. The fix has to be
at the information source, not the encoding.

**Rejected: keep the batch↔bank-line bijection and rely on the lag alone.**
Line counts alone would still give a solver `n_bank_lines == n_settlements` and
a near-perfect ordering prior. Foreign lines are cheap and remove both — and
they add a question the frozen set cannot ask at all: *is this credit even
ours?*

**Correction to the received account, recorded because precision matters.**
Measured: shuffling `engine/data/bank_statement.csv` changes the frozen
cascade's output not at all — 196/12/9/3 either way — because
`stage3_solver.run` re-sorts by `value_date`. "File order leaks" is **false**.
The real defect is stronger: unique dates at zero lag mean date-sorting alone
recovers the true settlement sequence, and a same-day collision is structurally
impossible. Fixing file order would have fixed nothing.

---

## 25. Calibration by selection: ties are a consequence of a price lattice, never a target

**Decision.** No row is ever minted to make arithmetic work. Every amount in
the ledger is drawn from a **price lattice** — price points crossed with a
quantity and a shipping line — so multi-closure arises everywhere as a
consequence of the draw. Ambiguity is `planted: false` throughout the corpus,
by construction. Every adjustment has a real cause: clawbacks tie to a
dispute's amount, fee reversals to a computed overcharge.

**The measurement, corrected.** The frozen planters minted **6 rows** — 3
adjustments at 1,856,136 / 2,117,064 / 3,295,351 paise, and 3 refunds. Two
perfect separators exist over the minted adjustments, both precision 1.000 and
recall 1.000: `description == 'Settlement processing fee'`, and the pair
`amount ≥ 1,856,136 AND dispute_id IS NULL`.

An earlier draft of this entry claimed the `amount` column **alone** separated
them, over 4 minted debits spanning 1,200,573–3,295,351. That was wrong twice:
the 1,200,573 row is organic, and `amount ≥ 1,856,136` alone reaches precision
**0.750**, because a genuine chargeback debit of 1,939,019 sits inside the
range. The correction is recorded rather than quietly applied — this file
exists to hold claims to evidence, including its own. The decision it supports
is unchanged, and if anything better motivated: the leak needed a column PAIR
to find, which is exactly why the audit searches pairs.

That is the third leak of this shape after `source_ref` and `notes.reason`, and
it generalises: *any row minted to make arithmetic work will leak, in some
coordinate, whether or not anyone anticipated which one.*

**Rejected: rejection-sample amounts until a tie exists.** The obvious way to
keep targets while dropping minted rows — and it is **D5 in a new coordinate**.
Batch composition is determined by the rule given the ledger, so the only lever
is the draw; conditioning the draw on a subset-sum coincidence localises a
distributional signature in exactly the window where the tie was wanted. That
is precisely what `corpus/leakage_audit.py` hunts, so the generator would have
contained a step the audit is built to fail.

**Rejected: keep minting but randomise the description strings.** Closes the
string coordinate and leaves the amount coordinate wide open, which is the
lesson of the frozen set restated rather than learned.

**One parameter was calibrated after a measurement, and it is recorded rather
than adjusted quietly.** The first lattice draft had 145 points for 262
payments — 66 duplicated *credit* values, which are swap-equivalent inside a
batch — and put the entire corpus **above** the hard regime: at pool ~20, 11 of
12 credits had multiple closing subsets and 7 of 12 exceeded 500. That collapses
axis A and is the mirror image of the frozen set's flaw. The lattice was
widened against **measured closure counts, before any resolver existed**, so
nothing about resolver performance was observable when it was picked — the same
ordering discipline the seeds and φ are held to.

---

## 26. `corpus/generator/sim.py` re-implements the loop and imports every primitive

**Decision.** Only the ~90-line batch-formation loop is re-implemented. The fee
model, `ceil_div`, the MDR tables, `add_working_days`, both selection rules and
every event dataclass are **imported** from the frozen `engine/simulator.py`.

**Why a new file at all.** Two things the corpus needs sit inside frozen
function bodies, not in rebindable module constants: `utr = f"{t}{sid[-6:]}"`
and a two-entry `SELECTION_RULES`. The monkeypatch pattern
`holdout/generate_holdout.py` uses cannot reach either.

**Rejected: unfreeze and parameterise `simulator.py`.** Destroys the freeze,
which is the strongest integrity property in the repo.
`tests/test_holdout_freeze.py` derives its entire value from the on-disk
generator being bit-identical to the one that produced the committed data; a
backward-compatible parameterisation still changes the hash and reduces the
claim to "trust me, the default path is unchanged."

**Rejected: copy `simulator.py` into `corpus/` and edit it.** Duplicates ~260
lines of fee and eligibility arithmetic that must never diverge, and gives a
future spec fix two places to land. Importing the primitives means the
arithmetic *cannot* drift; only the loop can, and the loop is under test.

**The drift risk is closed by differential test, not by review.**
`corpus/tests/test_conformance.py` asserts exact equality with the frozen
simulator at the frozen configuration point, on the frozen ledger under both
rules and on 25 seeded random ledgers — 29/29 passing. **The frozen
configuration is therefore a corpus axis point**, and every other point is a
controlled deviation from a verified baseline rather than an unanchored new
artefact.

---

## 27. `random_valid` samples uniformly from a band, and the band is a stated assumption

**Decision.** `S ~ Uniform{ S ⊆ E(t) : φ·available ≤ Σcredit(S) ≤ available }`,
φ = 9/10, sampled exactly by a counting DP over achievable sums. One axis point
runs at φ = 0.

**Why a band.** `Σcredit(S) ≤ available` alone admits `S = ∅`: money would
rarely settle, pools would grow without bound, and pool size would become an
*outcome* rather than a controlled variable — confounding axis A with axis C.

**Rejected: uniform over all feasible subsets.** By mass it concentrates near
half the rows, draining about half the pool per batch. Same confound.

**Rejected: shuffle the pool then FIFO-fill.** Simple and drains near-maximally,
and rejected specifically: it is biased toward many-small-rows, so a solver
preferring cardinality-maximal closing subsets systematically agrees with it.
That is §4's premise sharing reintroduced through the back door.

**Rejected: random tie-break inside `max_under_cap`.** Not a third rule — it is
`max_under_cap` with a different tie-break, and it keeps the maximality
objective the solver shares. It does not test what axis C exists to test.

**Flagged.** At φ = 0.9 the rule still weakly shares "bigger is likelier" with
any resolver preferring large closing subsets. φ is the knob trading economic
realism against premise independence; it is recorded per dataset and was
calibrated against measured mean pool size only.

---

## 28. Ground truth records `composition` and `closure` as two separate facts

**Decision.** `composition` is the subset the generator selected — a fact about
the generative process, exact at any pool size. `closure` is every subset
closing to the payout under **no objective** — a fact about the reconstruction
problem, capped at 500 with `recoverable ∈ {unique, not_unique, unknown,
no_closure}` and `unknown` first-class.

**Why the frozen key cannot express this.** It records
`tying_decompositions` — subsets tying at the *maximum*. §2 of the defect
report measured what that means: two primary credits had three closing subsets
each and were recorded, and reported, as determinate. A register built with an
objective can only ever confirm the objective.

**Rejected: score against `composition` alone.** Rewards guessing where the
answer is unrecoverable, which is exactly how a 1.000 precision the defect
report calls a property of the dataset got reported as an engine property. Both
fields exist, and a resolver returning a confident answer where
`closure.count > 1` is **wrong even when it matches `composition`**, because it
cannot have known.

**Rejected: keep `tie_limit=64` plus a `truncated` boolean.** One boolean
cannot distinguish 65 ties from 10⁷, and at pool 60 every batch is truncated so
the flag carries no information at all.

**Rejected: cap the corpus at pool 28 and drop A=40/60.** The safe choice, and
rejected deliberately: closure uniqueness collapsing with pool size is the one
variable already measured to be interesting, and dropping it would reproduce
the frozen set's central flaw.

---

## 29. The leak audit gates on effect size and reports significance beside it

**Decision.** A separator fails the build at precision ≥ 0.90 and recall ≥ 0.50.
The hypergeometric p-value, Bonferroni-corrected **within family**, is reported
as `certified` and does **not** gate. Classes too small to be certifiable are
named UNDERPOWERED rather than reported clean.

**The measurement that forced it.** `description == 'Settlement processing fee'`
isolates frozen minted rows at precision 1.000, recall 0.500 — p = 8.79e-06
against α = 3.79e-06 over 2,641 single-column hypotheses. It **misses
significance by a factor of 2.3** and it is a leak anyone can exploit in ten
seconds. A six-row class in a 240-row file cannot be certified by a
thousands-of-hypotheses search; that is a statement about power, not about the
rows being clean.

**Rejected: gate on Bonferroni significance.** Would have passed the frozen set
on D5 — the exact defect the audit exists to catch. The costs are asymmetric: a
false alarm costs one regeneration, a missed leak costs the submission.

**Rejected: a deny-list of known leaky tokens.** Four leaks were closed that way
one at a time. The fifth will not be a token.

**A fifth family the other four cannot express: class efficacy.** D7 is not a
leak — it is a class that is perfectly hidden and simply does not do what it
claims. A separator search cannot find it because there is nothing to find, so
efficacy is asked as its own question, and the audit reproduces the frozen
credit deltas (−8,711 / −3,670 / 0 / +11,732) unprompted.

**Validation.** `--validate-frozen` must rediscover D4, D5, D6 and D7 without
being told what to look for. It does. The D5 class is derived by driving the
frozen generator as a library and diffing row ids across the planter calls —
deriving it from the leak itself would assume the answer.

---

## 30. The corpus is a screening design, and the untested cells are named

**Decision.** 14 datasets, not the full 5 × 4 × 3 = 60: a spine at the
configuration closest to the frozen set, one factor moved at a time, and two
interaction cells chosen for cause (`A40_B50_Cmax`, because the branch that
produced the 50 wrong rows needs coverage < 100% *and* D1 needs a big pool;
`A40_B100_Crandom`, because no objective can help at a pool size where
non-uniqueness is measurable).

**Rejected: the full grid.** Closure enumeration at pool 60 already dominates
generation time, and 60 cells buy interaction terms nobody has a hypothesis
about at the cost of the cells that test something specific.

**Rejected: a single "hard" dataset.** One point cannot show a gradient, and
the gradient is the finding — whether confidence tracks determinacy is not
answerable at one pool size.

**Named gaps, because silence reads as ignorance.** B × C is untested entirely.
The GST leg is barely improved and **D9 stands** — all four axes are
settlement-side, so any GST claim in a headline remains substantially unearned,
and the fix is a fifth axis this corpus does not have. And there is **no
wrong-bank-side class**: the corpus plants an attestation that is wrong but
never a case where the two sources contradict and truth is on the *bank* side,
so "two independent sources agree" is not tested at the one point where the
direction of the disagreement matters. That is the most significant single gap.

---

## 31. The contract was amended once after generation began, and it is dated

**Decision.** `ReconstructibleInstance` and oracle gate **G8** were added on
2026-08-24, *after* the corpus had been generated. The amendment is dated in
`RESOLVER_CONTRACT.md` §6.4 and in `types.py` rather than folded into the
original text, because this contract's whole claim on being trustworthy is
that it was written before the data.

**Why it was necessary.** Measured on the built corpus:

| axis point | `DeterminedInstance` | lines with unique complete closure |
|---|---:|---:|
| `A20_B100_Cmax` | 10 | 11 (all attested) |
| `A20_B75_Cmax` | 8 | 12 (3 unattested) |
| `A20_B50_Cmax` | 5 | 11 (5 unattested) |
| `A20_B0_Cmax` | **0** | 11 (**11 unattested**) |

At 0% attestation coverage **every gate was vacuous.** §6.3's theorem forces
`|Verified| = 0`, so the wrong-`Verified` and independence gates had nothing to
range over; and `DeterminedInstance` requires the attestation, so §6.1's
abstention gate had an **empty subpopulation**. A resolver returning
`Unresolved` to everything scored perfectly on the one axis point that is
purely about reconstruction — and that is the cell where the branch which
produced all 50 wrong answers actually lives.

**The theorem is what disguised it.** §6.3 predicted the cell would contain no
`Verified`; the prediction came true, and nothing was learned. Stating a
theorem and then not checking what it leaves *unmeasured* is its own failure
mode, and it is worth naming because it is subtle: the cell looked correct
precisely because it behaved as predicted.

**What the amendment does not touch.** No outcome semantics, no existing gate,
no generated dataset. It is derived from closure registers already present in
every ground-truth key, so nothing was regenerated to make it true. That is
what keeps it an addition rather than a re-cut of the benchmark after seeing
results — and the distinction is the whole point, so it is stated rather than
assumed.

**Rejected: leave the cell ungated and name it as a gap.** Defensible, and it
preserves the contract-before-corpus ordering perfectly. Rejected because the
0% cell is the one the brief singles out as pure reconstruction, and shipping
the most-cited cell with no falsifiable gate would be shipping the abstention
loophole in the one place it matters most.

**Rejected: drop the B0 axis point.** If a cell cannot be gated it arguably
should not ship. Rejected because the cell is gateable — it just needed the
right subpopulation — and dropping it would have removed the pure-
reconstruction extreme rather than measuring it.

---

## 32. The corpus was regenerated five times, because its own audit failed it four

**Decision.** `corpus/leakage_audit.py` gates the build. A dataset that fails
its own audit does not ship: it is regenerated or the class is dropped. Three
rounds of findings, all on the corpus rather than on the frozen set, all fixed
at the **same committed seeds** — fixing a bug is not reselecting a seed.

**Round 1 — a real leak, cleaner than the defect it was written to prevent.**
Orphan ERP invoices were emitted with a blank `order_id`, so
`order_id IS NULL/blank` isolated the class at precision 1.000, recall 1.000.
D6 in a new coordinate, and worse: D6 needs a rank check to find, this needed
one column. An orphan now carries an order reference in the merchant's own
format, drawn from the same alphabet and length as a gateway order id. What
makes it an orphan is that **no payment references it** — which is the
reconciliation work rather than a shortcut to the label.

**Round 2 — a second real leak: `narration CONTAINS 'clo'`.** Every foreign
bank credit named a different remitter, so *"is this credit even ours?"* was
answerable by reading the counterparty instead of by reconciling. Half the
foreign credits now come from Razorpay too — a fee refund, a reversal
re-credit, an advance. A merchant genuinely **can** rule out a credit from an
unrelated payer; what the corpus must not do is make that the only case.

**Round 3 — two flaws in the audit itself, not the data.**

*Unit of analysis.* `d04_unattested_settlements` was expressed as the *rows of*
unattested batches, and a time-window predicate reached 94% precision on 69% of
them with a p-value that treated ~69 clustered rows as independent
observations. They are not independent — they are one observation repeated.
Attestation is a property of a **settlement**, so the class is now expressed at
settlement level, as `d03_wrong_attestation` already was.

*Base rate.* At 0% coverage every settled row is unattested, so
`settled == True` reached precision 1.000, recall 1.000 — at lift **1.2×**.
That is not a leak, it is the definition of the axis point. The audit now
requires `MIN_LIFT = 2.0` and reports any class covering more than half its
table as **DEGENERATE** rather than as either clean or leaking.

**Round 4 — a third real leak, and the subtlest.** Settlements that lost their
attestation were reported under a `RZPX…` reference while attested ones carried
the bank's `RATN…`. Sorting `reported_reference` separated the two at precision
1.000. The prefix existed only because the generator needed a value meaning
"not the bank's reference" — **a field whose SHAPE announces what the generator
was doing**, which is the D5 lesson in a new column. The PSP-internal reference
now takes the same shape as a real bank reference and differs only in being a
value the bank never issued, so discovering that a settlement is unattested
requires failing to find a matching bank line. That is the reconciliation work
rather than a read of the prefix.

It is worth naming why this one was easy to defend and still wrong. A real
PSP's internal reference genuinely does look different from a bank UTR, so the
separator was *realistic*. But realism is not the test. The test is whether the
field reveals the generator's intent, and a prefix that exists to mean "this
one is in the withheld group" does.

**Rejected: exempt the classes that failed.** The fastest route and the exact
habit that produced four leaks in the frozen set — each closed by adding one
token to a deny-list. An exemption is a deny-list entry wearing a different
hat.

**Rejected: lower the thresholds until the corpus passes.** This is the
seed-sweeping failure in another coordinate, and it would invert the audit's
purpose: the thresholds exist to be met, not to be met halfway.

**The point worth keeping.** Rediscovering D4–D7 shows the audit is *sensitive*.
Finding four previously unknown problems in the corpus it was built to protect
— two real leaks and two flaws in its own statistics — is the better evidence,
because nobody knew those were there.

---

## 33. The primary answer to the `GROUP BY` finding is PSP ABSENCE, not PSP deceit

**Decision.** The cell that makes reconstruction necessary is one where the PSP
artefact is **not there** — `A20_Bnone_Cmax` and `A40_Bnone_Cmax` carry no
`settlement_id`, no `settled`, no `settled_at`, no `settlement_utr` and no
`settlement_report.csv`. Absence is stated in `CORPUS_SPEC.md` §6.5 as the
*primary* justification for the whole reconstruction architecture; the false
attestation (§34) is secondary.

**Why.** `CHECKPOINT.md` §0.1 measured that a fifteen-line `GROUP BY` scores
168/168 on the first fourteen datasets, because `settlement_id` is populated on
every settled row and no dataset ever plants a false one. The obvious repair is
to make the PSP lie more often. That repair is wrong on the merits: **PSPs do
not systematically misreport composition**, a Razorpay engineer will say so in
the first minute of the panel round, and a benchmark whose difficulty rests on
an untrue premise about the counterparty is a benchmark about nothing.

What is true and common is that the artefact is missing: a second gateway with
no recon API, a historical period predating the feed, an acquirer statement
held alone, a merchant reconciling a bank account rather than a dashboard. In
that regime there is money in a bank account, a ledger, and nothing joining
them. Reconstruction is the only path and `Reconstructed` is the only positive
outcome reachable.

**All four settlement columns are dropped together**, because they are one
assertion written four ways. Dropping only `settlement_id` would leave
`settled_at` as a perfect group key — the same triviality one column over, and
the same error §0.1 records.

**Rejected: make the PSP lie on a large fraction of batches.** Unrealistic, and
it converts the benchmark's central difficulty into a premise the reader does
not accept. One planted restatement per dataset (§34) is the realistic dose.

**Rejected: blank `settlement_id` while keeping `settled` and `settled_at`.**
Grouping on `settled_at` recovers the batch exactly. This is the cheap version
of the fix and it fixes nothing.

**Rejected: emit an empty `settlement_report.csv` with only a header.** An
empty file still asserts "the PSP made no claims about this period", which is
itself a claim, and a resolver could legitimately act on it. Absence has to be
absence.

**Rejected: regenerating the original fourteen without `settlement_id`.** The
seeds and the data are frozen and the ordering is the integrity argument. New
shapes are new files at new seeds. The fourteen remain as they are and remain
reported, `TRIVIAL` label included.

**The cost, accepted and recorded.** Contract §2.4 permits only `Verified` to
consume, and `Verified` is unreachable without an attestation, so the pool
grows monotonically across the window and closure becomes non-unique after the
first few credits. A sound resolver will decline most of these lines. That is
the measurement — *how much of reconciliation the attestation is actually
doing* — and not a defect of the cell.

---

## 34. The false attestation is a RESTATEMENT, swapped at exactly equal net

**Decision.** `corpus/datasets_v2/` is the fourteen axis points regenerated at
**new seeds committed beforehand**, each carrying one batch whose
`settlement_id` is written onto rows that are not its true composition. The
original fourteen are untouched. Both families ship and both are scored.

The plant is built by CP-SAT: a subset `S` of the true composition is swapped
for a set `T` of rows that no batch claims, subject to `net(S) == net(T)` in
exact integer paise, minimising `|S| + |T|`.

**Two properties, both load-bearing.**

*The arithmetic still closes.* If it did not, the naive baseline's one existing
check would catch the plant and the class would test nothing. As built, the
attested rows sum to the bank credit exactly and **no sum check can see it**.

*It is discoverable by reconciliation rather than by grepping.* Every donated
row was created strictly after the **bank's** value date for that line. A row
that did not exist when the money left cannot have been in the money that left.
That is a contradiction between the PSP's `created_at` and the bank's
`value_date` — two parties — so the plant is found by exactly the independent
check `Verified` is defined to rest on, and missed by exactly the resolver the
contract exists to catch.

**Rejected: swap for rows drawn from the batch's own eligible pool.** This is
the tempting version, because the closure register already enumerates rival
closing subsets and one is free to take. It produces a false attestation that
is **undetectable in principle**: same net, all rows eligible, nothing claimed
twice, no temporal contradiction. Any resolver that trusts a composition claim
— including one that obeys this contract to the letter — returns a wrong
`Verified`, which oracle gate G1 calls a build failure. That would be a
genuinely interesting result about the contract's `Verified` being unsound, and
it is **named as a gap rather than planted**, because manufacturing a
guaranteed G1 failure teaches less than measuring whether a discoverable one
gets discovered. Recorded here so the easier reading — "they picked the version
their resolver can pass" — has the actual reason next to it.

**Rejected: steal the donated rows from a later batch.** Then the later batch's
attestation stops closing and the discrepancy surfaces at a *different* bank
line, damaging two lines with one plant and confounding which line the class is
about.

**Rejected: minting rows to make the net work.** Defect D5, and the reason the
frozen calibration rows are greppable. Where CP-SAT finds no exact swap the
class is recorded `planted: false` with the reason and the dataset ships
without it. That happened once, at `datasets_v2/A20_B0_Cmax`, where no batch is
attested and there is no correct attestation to restate.

**Rejected: corrupting `settlement_report.csv` instead.** That is the class the
corpus already had, and §0.1 measured what it is worth: it corrupts a scalar
amount, never a row's membership, so the trivial predicate is unaffected by it.

**Known consequence, not a defect.** On a falsely attested line the contract
forces a choice: `AttestationDiscrepancy` says *the record is wrong* and
carries no composition, while `Reconstructed` could still name the true rows
from unfiltered closure. **The vocabulary cannot say both.** A resolver
reporting the discrepancy forgoes a reachable answer. This is a real limitation
of the outcome set, it is named here rather than fixed by amending the contract
during a phase whose whole point is not to build another layer of apparatus.

---

## 35. The triviality check is a permanent output, not a one-off audit

**Decision.** `corpus/triviality_check.py` runs the naive `GROUP BY` baseline
against **every** dataset, old and new, and reports `TRIVIAL` / `PARTIAL` /
`NOT TRIVIAL` / `N/A` per dataset as standard output. `--gate` fails only when
*every* dataset is `TRIVIAL`.

**Why a new file rather than a sixth family in `leakage_audit.py`.** The audit's
five families all ask *"does a trivial predicate identify this planted class?"*
over a per-class contingency table. The question that was missed is one
coordinate up — *"does a trivial predicate solve the task?"* — and it is scored
against the *answer key's compositions*, not against a class. Bolting it into
the class-audit machinery would have meant expressing the whole task as a
planted class, which it is not.

**Why individual `TRIVIAL` datasets are not a build failure.** The original
fourteen are all `TRIVIAL` and should be: the easy regression baseline is worth
having, and any sound resolver must score near-perfectly on it. What was wrong
was not that they are easy — it was that nobody had **measured** that they are
easy, and conclusions were drawn as though they were hard. The label is the
fix. The gate fires only if the whole benchmark is easy, which would mean it is
measuring a handicap the engine under test imposed on itself.

**Rejected: gating every trivial dataset out of the corpus.** That deletes the
regression baseline and, worse, would have deleted fourteen datasets to make a
number look better — the exact move the seed-commitment protocol exists to
prevent.

**Rejected: reporting it once in `CHECKPOINT.md` and moving on.** The finding
was available for the whole previous phase and cost ten minutes to obtain. A
prose paragraph is not a mechanism. A script that runs on every dataset is.

---

## 36. The resolver is a separate package that cannot see the answer key, and the isolation test was watched to fail

**Decision.** `resolver/` imports `resolver_contract/types.py` and nothing else
from this repository. It may not import `matching/` (the frozen engine),
`corpus.generator` (which knows how the data was made), `corpus.oracle` or any
baseline. `resolver/loaders.py` is the only module that performs file I/O, and
`ground_truth.json` is on a named `FORBIDDEN` list rather than merely absent
from the code.

Scoring lives in `corpus/score_resolver.py`, on the far side of the boundary.

**Why a new test file rather than an entry in an existing allowlist.**
`engine/tests/test_no_leakage.py` scans `engine/`, `matching/` and `eval/`.
`tests/test_isolation.py` enforces the same over `matching/` by AST. **Neither
covers `resolver/`.** A suite that does not scan a directory says nothing about
that directory, and assuming otherwise is exactly how defect D2 shipped: an
unguarded `elif` that could not execute on the only dataset in the repo, inside
a 268-test suite that passed. So `resolver/tests/test_isolation.py` enforces
the rule over this package by four independent mechanisms: source text with
docstrings stripped, the AST, the static import list, and the live
`sys.modules` graph after importing every module.

**The test was verified to fail.** A `json.loads((… / "ground_truth.json")
.read_text())` was added to `resolver/resolve.py` and the suite re-run: three
tests failed and each named the file and line. A test nobody has watched fail
is a test nobody has run. The violation was then reverted.

**Rejected: adding `resolver/` to `GROUND_TRUTH_ALLOWLIST`.** The allowlist is
for `eval/` modules that are *permitted* to read the key. A resolver is never
permitted, so it does not belong in a list whose purpose is to grant the
permission.

**Rejected: one shared isolation test parameterised over every package.** It
reads as broader coverage and is worth less: the rules genuinely differ
(`eval/` may read the key, `matching/` and `resolver/` may not, and `resolver/`
additionally may not import `matching/`), and collapsing them into one
parameterised sweep is how a package quietly ends up on the permissive branch.

---

## 37. Reversals are resolved in two passes, and the scan runs first

**Decision.** Pass one reads the **bank file alone** and finds every debit that
revokes an earlier credit: equal and opposite amount, later value date, within
seven days, each credit claimed at most once. Pass two resolves credits in
posting order. A revoked credit is reported as
`AttestationDiscrepancy(credit_reversed)`, which assigns nothing and consumes
nothing; the debit line itself is `Unresolved(other)` naming the credit that
carries the finding.

**Why it cannot be a single date-ordered pass.** `DECISIONS.md` §19 measured
this on held-out data: a reversal makes an earlier resolution wrong
*retroactively*. A single forward pass has already consumed the rows by the
time the reversing debit arrives, and D2 then propagates the damage — one
reversal, two damaged bank lines, 50 misplaced rows. Running the revocation
scan **before** any resolution means the resolver never forms the claim it
would have to retract.

**Rejected: (b) refuse to consume until the window closes.** This is the other
option and it is defensible: hold every assignment provisional, decide at the
end. It was rejected because non-consumption is exactly what makes the pool
grow monotonically, and a growing pool drives closure non-uniqueness, so a
resolver that refuses to consume converts a solvable window into an ambiguous
one and reports abstention as caution. The PSP-absence axis points measure that
effect directly, because there `Verified` is unreachable and consumption never
happens — see §33.

**Rejected: revisit and retract after resolving.** Equivalent in outcome and
worse in evidence: it leaves a retracted `Verified` in the run's history, and
the contract deliberately makes a wrong `Verified` a build failure rather than
a state to pass through.

**Rejected: treating the reversal as an ordinary unmatched debit.** It is the
most common real recon exception (`SETTLEMENT_SPEC.md` §10) and the single
highest-value thing a resolver can say about it is *the record is wrong*, not
*I could not explain this line*.

**Named limitation.** The seven-day window is a modelling choice. Two lines of
equal and opposite amount far apart are two transactions, and calling them a
reversal would invent a finding; a reversal posted later than seven days is
missed. The corpus posts reversals one to four days after the credit, so the
window is not tested at its boundary.

---

## 38. Tier B exists; residual reconstruction does not, and the reason is D2

**Decision.** The resolver has three tiers. Tier A is used when the PSP's
settlement report names this bank line by the bank's own reference. Tier B is
used when the recon rows carry a `settlement_id` — a composition claim exists —
but no report row names the line, so the link from batch to bank line rests on
the amount alone; where two unconsumed settlements net to the same amount it
returns `Ambiguous` rather than choosing.

**What is NOT built: anchoring on an attested core and reconstructing a
residual over unattested rows.** Attestation in this corpus is a property of a
SETTLEMENT, never of a row: `corpus/generator/build.py` varies coverage by
sampling settlements, and no dataset has a batch that is half attested. The
residual path would therefore be a branch **no dataset can execute** — which is
precisely what defect D2 was, and shipping a second one while citing the first
would be indefensible.

**Rejected: build it anyway and unit-test it on a synthetic fixture.** A
fixture written by the same person, in the same hour, to exercise the branch
they just wrote, tests that the branch runs. D2 passed 268 tests.

**Rejected: adding a row-level attestation axis to the corpus so the path
becomes reachable.** That is the next layer of apparatus, and this phase's
standing instruction is to ship rather than build one. It is named as a gap in
`CORPUS_SPEC.md` instead.

**Consequence, stated.** Tier B is what makes withdrawn contract §6.3 concrete:
at 0% report coverage the composition claim is still on the rows, it still
entails a checkable prediction about the bank's amount, and `Verified` is
reachable. The old §6.3 theorem said that cell must be empty and gate G5
enforced it; both are withdrawn, and this tier is the code that would have
tripped the withdrawn gate.

---

## 39. `complete` means CP-SAT exhausted the search space, and nothing weaker

**The defect, as shipped.** `resolver/enumerate_closures.py` computed

```python
timed_out = status == UNKNOWN or (elapsed >= time_budget and status != OPTIMAL)
complete  = not hit_cap and not timed_out
```

`elapsed` is measured **outside** the solver with `perf_counter`, while CP-SAT
enforces its own `max_time_in_seconds` **inside**. When the solver stopped on
its internal limit at 9.98 s of a 10 s budget and returned `FEASIBLE`,
`elapsed >= time_budget` was False, `timed_out` was False, and **a truncated
enumeration was recorded as exhaustive.**

**The repro.** `corpus/datasets/A40_Bnone_Cmax` bank[7], during the first
scored run, with a second CP-SAT process on the machine: 194 subsets returned
with `complete=True` and the true composition **not among them**. Oracle gate
G3 named it exactly — *"the truth is absent from a COMPLETE candidate set of
194 — the resolver's enumeration is wrong, not merely undecided."* Run alone,
the same line correctly reports 200 subsets and `cap_reached`. The true
composition is in the pool at that line (42 rows of a 209-row pool, verified
directly), so the enumeration, not the pool, was at fault.

**What it should have been, and now is.**

```python
complete = status == OPTIMAL
```

With `enumerate_all_solutions`, `OPTIMAL` is CP-SAT's own statement that it
exhausted the search space. Everything else — `FEASIBLE`, `UNKNOWN`, a
cap-triggered `StopSearch` — means it stopped early, whatever any external
clock says.

**Why this is the defect class this repository exists to catch.** `complete`
is the difference between "exactly one subset closes" and "one subset was
found before I gave up". `Reconstructed` requires the first; the contract
spells that out in §4.5 and `Closures.is_unique` enforces it. The old test
claimed the stronger epistemic state on weaker evidence — the identical shape
as `Determinate` meaning "unique among subsets maximising applied debits", as
`BalanceProof` proving an identity that cannot fail, and as withdrawn §6.3
asserting a theorem it never measured. **It was written into the resolver built
to prevent it, by someone who had just catalogued the other three.**

**What else it could silently have affected, named rather than waited for.**

* **A false `Reconstructed`.** A truncated set of size one satisfies
  `count == 1 and complete` under the old test, and `Reconstructed` would then
  assign a composition on an enumeration that never proved uniqueness. Run 1
  produced **2 `Reconstructed` in total, of which 1 was wrong** — an adoption
  of a foreign bank line at `datasets/A20_B50_Cmax`, a line that is not a
  settlement of ours at all. Whether that specific outcome was produced by this
  bug is checked by the re-run, not asserted here.
* **A false `rival_count_is_lower_bound = False`** on a `Verified`, which would
  report a rival closure count as exact when it is a floor — understating how
  weak the corroboration was, in the one field contract §3.3 makes mandatory
  precisely so weakness cannot hide.
* **`Ambiguous` with `complete=True`**, whose `common_rows` is then computed
  over a set that is not all the candidates. `common_rows` is never assigned
  from, so this is a reporting error rather than a soundness one — but it is
  the property D3 turned into 45 unwarranted assignments in the previous
  engine, so it is named.
* **Run-to-run variation with machine load**, since the trigger is a race
  between two clocks. Determinism is claimed throughout this repo and it was
  not holding here.

**Rejected: also replacing the wall-clock budget with CP-SAT's deterministic
time.** It would remove the load-dependence entirely and it is the better
long-run answer. It also changes *every* number rather than only the
mislabelled ones, in a component that had already been frozen and scored. The
scope taken was the one-line correctness fix; the determinism improvement is
named as open work.

**Rejected: reporting run 1 and leaving the code alone.** Preserves the
freeze-before-scoring ordering most literally, and ships a resolver that can
claim an exhaustive enumeration it did not perform.

**Both runs are published.** `corpus/ORACLE_RESULTS_RUN1.md` and
`corpus/oracle_results_run1.json` are the pre-fix run, kept rather than
discarded, and `corpus/THREE_SYSTEMS.md` carries the delta attributed to this
fix. A before/after pair is stronger evidence that a fix is real than a single
clean number, which is the same standard applied to every other correction
here.

---

## 40. `CorrectlyUnmatched` splits into `ProvenUnmatched` and `OpenBreak`, and the admission test is entailment rather than accuracy

**Decision.** Contract §4.6 is superseded by a dated §4.7 amendment. The single
outcome becomes two: `ProvenUnmatched`, a positive claim gated at zero by a new
oracle gate G9; and `OpenBreak`, which asserts nothing, carries a classified
reason, an age, an owner and a close condition, and is therefore never gated on
correctness. Exactly two reasons are admitted to `ProvenUnmatched` —
`NOT_CAPTURED` and `NETTED_OUT`.

**Why.** `CorrectlyUnmatched` asserted one thing and was used for two: *"the
ledger entails no bank credit exists"* and *"I did not place this row"*.
Measured over all 30 datasets, 4,994 claims, full enumeration: 45.7% accurate
overall, splitting into a positively derived branch at 97.6% (1,828/1,872) and
a residual fallthrough at 14.6% (455/3,122). `ROLLED_FORWARD` — defined in
`types.py` as *"eligible, not selected"*, a residual by construction, four
lines under a docstring demanding every reason be "DERIVED, not assumed" — was
right **17 times out of 2,397**.

**The measurement that set the admission test.** Correcting the derivations to
transcribe `engine/simulator.py` exactly makes the reasons **more accurate**
(36 wrong → 10) and the soundness gate **five times worse** (8 rows that
actually settled → 64). A corrected `dispute_held` promotes 142 rows out of the
residual, where they assert nothing that is scored, into a derived branch,
where they become positive false claims. Accuracy was never the property this
outcome needed. The gate is entailment.

**Rejected: keep one outcome and fix the reasons.** This is the option the
measurement above refutes. It produces a *better classifier* and a *worse
system*, and it was the plan of record until the numbers came back.

**Rejected: admit `dispute_held` to `ProvenUnmatched`, narrowed to
`status == under_review`.** That narrowing is genuinely clean on this corpus —
199 rows, 0 counterexamples, against 345 rows and 64 counterexamples unnarrowed.
It is still rejected. The clean split is over *current* dispute status read
against a *past* horizon, which is the same bi-temporal error the branch was
already making (§41), so its soundness is a property of this corpus rather than
of the rule. And the phase semantics are against it: `SETTLEMENT_SPEC.md` §6.1
has `chargeback` clawing back *after* settlement, and all 31 lost chargebacks
in the corpus settled and were then reversed. A hold cannot entail
non-settlement at any level of implementation quality.

**Rejected: admit `not_yet_eligible`.** This one *earns* a gate and does not
get one. It has 0 counterexamples in 952 rows and the soundness is provable
rather than lucky: the resolver's horizon is the last bank `value_date`, the
answer key's is the last batch time, and the former is always later, so the
test is strictly stronger and can miss but never false-positive. It is an
`OpenBreak` anyway, because `ProvenUnmatched` means *no bank credit exists* and
a not-yet-eligible row's bank credit exists next Tuesday. Gating a temporary
state as a permanent proof is how the distinction rots. The strength of the
evidence is preserved in a `provable_within_window` flag, not in the outcome
type.

**Rejected: drop `UNEXPLAINED`, or widen the other reasons until it empties.**
`UNEXPLAINED` is a real, reported category. Predicted at 593 rows. A residual
given a name that sounds like a derivation is precisely how `ROLLED_FORWARD`
happened, and eliminating the honest bucket is how it would happen again.

**Rejected: report a single "unmatched" total.** `ProvenUnmatched` and
`OpenBreak` are never summed. A total over an assertion and a non-assertion
recreates exactly the conflation the amendment undoes.

**What this admits.** Every soundness claim in this repository before now —
"0 wrong answers", repeated in the README, `THREE_SYSTEMS.md` and
`CHECKPOINT.md` — meant **"0 wrong `Verified`"** and nothing more, while a
second outcome type that also asserted something was wrong 2,469 times and no
gate looked at it. G9 exists because that was true and unstated.

---

## 41. The `netted_out` predicate is transcribed from the frozen simulator, not paraphrased from the spec

**Decision.** `resolver/breaks.py:netted_out_payments` copies
`engine/simulator.py:366-376` literally: `sum(refund.amount) == payment.amount`
**and** `all(refund.created_at <= eligible_at)`. Both halves, exact equality,
against the **gross** amount.

**Why.** The first resolver paraphrased the same rule as
`sum(refund.debit) >= payment.credit` with no timing test. Three independent
divergences, each sufficient alone to produce a false claim, and all 8 of the
G9 failures in the audit had all three:

| divergence | consequence |
|---|---|
| `>=` instead of `==` | an over-refunded payment reads as netted; it settles |
| `credit` (`amount − fee`) instead of `amount` | a refund short of gross by less than the fee reads as full. Measured: refunds of 2,014,800 against a payment of 2,014,900 — one rupee short — passed |
| no timing test | a refund raised weeks after settlement counts as having prevented it |

**Rejected: reading `SETTLEMENT_SPEC.md` §3 and implementing from the prose.**
That is what produced the paraphrase. The spec's prose is correct — it says
plainly that a partially refunded payment "settles at **full** `amount − fee`"
— and the implementation still drifted, because prose does not say which of
`amount` and `credit` a comparison should use. `engine/simulator.py` is the
normative artefact and it is frozen, so transcription costs nothing and drift
becomes a test failure. `test_the_predicate_matches_the_frozen_simulator_on_
every_dataset` asserts set equality with the answer key's own `netted_out`, so
drift in either direction fails.

**Watched to fail.** The predicate was deliberately regressed to
`sum(debit) >= credit` and `test_an_OVER_refunded_payment_does_not_net_out`
failed immediately, as did the frozen-simulator equality test. Reverted.

---

## 42. `attested_row_ids` and `Contradiction.row_ids` answer different questions

**Decision.** `Contradiction.row_ids` carries only the rows *implicated in the
contradiction*. `AttestationDiscrepancy.attested_row_ids` carries **every row
the PSP attested to that bank line**, whether implicated or not. Defined in
contract §4.7.5, having never been defined anywhere before.

**Why.** `RESOLVER_CONTRACT.md` §4.2 named no field, and an undefined field
acquired three meanings across five call sites:

| kind | n | rows named | rows in the true batches |
|---|---:|---:|---:|
| `claimed_credit_not_on_statement` | 22 | 688 | 688 |
| `temporal_impossibility` | 10 | **13** | **294** |
| `credit_reversed` | 30 | **0** | 783 |

Real cause-pointer coverage was **701 of 1,765 rows (39.7%)**. The
`OpenBreak` cause pointer reads `attested_row_ids`, so without the separation
`UPSTREAM_UNRESOLVED` could reach under 40% of the rows it should and the
clustering that makes the exception queue usable would not exist.

**Rejected: patch `_reversed_credit` alone.** It was the visible hole and
fixing it raises coverage to roughly 83%, which is why it is the tempting
option. It leaves `temporal_impossibility` naming 13 rows out of 294 and
*silently* under-pointing — a worse failure than the empty one, because an
empty field is obviously empty.

**Rejected: make `attested_row_ids` mean the offending subset everywhere.**
Consistent, and it destroys the only field that can answer "what did this
finding block".

---

## 43. `UPSTREAM_UNRESOLVED` is a sixth break reason, and absence datasets do not get one

**Decision.** The standard five break reasons — `MISSING_SOURCE`,
`TIMING_DIFFERENCE`, `MAPPING_ISSUE`, `UNEXPECTED_CHANGE`, `TRUE_ERROR` — gain
a sixth, `UPSTREAM_UNRESOLVED`: this row's disposition depends on a **bank
line** whose own outcome is unsettled. It closes when the causing line becomes
`Verified` or `ProvenUnmatched`, at which point every row clustered under it is
re-evaluated together.

**Why.** 2,461 rows cluster under 83 causing bank lines, mean 29.7 rows per
cause. Reported flat the queue is noise; clustered it is 83 items, which is how
exception queues are actually worked. None of the five fits: the source is
present and legible, the rows are inside the window, they map fine, nothing
about them changed, and no error has been established.

**Rejected: `TRUE_ERROR`.** Asserts an error nobody has demonstrated.

**Rejected: `UNEXPLAINED`.** Hides the one thing actually known about them,
which is precisely *why* they are open.

**Consequence accepted, not worked around.** At a PSP-absence dataset no
attestation exists, so no cause is nameable and every unplaced row falls to
`UNEXPLAINED` — roughly 689 rows the ground truth *can* attribute to an
`Unresolved` line but the resolver cannot. The committed prediction in
`investigation/DERIVED_BRANCH_AUDIT.md` §4.3 puts 2,405 rows under
`UPSTREAM_UNRESOLVED`, and that figure was computed with a ground-truth cause
pointer, so it is an **upper bound on what the resolver can derive**, not a
forecast of what it will. The gap is reported rather than closed. Building a
"was in the candidate pool of these Unresolved lines" pointer would be new
apparatus of exactly the kind this phase is under instruction not to build, and
it is many-to-one, so it would weaken the field's meaning to raise a number.

---

## 44. The reference-frame defect class: a predicate whose two sides come from different frames

**The class.** A predicate reads the **wrong reference frame** — wrong clock,
wrong horizon, wrong quantity, wrong pool — while looking locally correct at
every call site. Each instance produced a claim *stronger than the evidence
supported*. Each was invisible to review, because nothing about the line of
code is wrong; what is wrong is what the two sides mean.

**The rule this implies, and it is the only part of this entry that is a
decision rather than a finding:**

> Every predicate over a mutable, derived, or time-dependent quantity must
> name **in code** which frame it evaluates in. A comparison whose two sides
> come from different frames is a defect **even when it currently agrees** —
> because the agreement is then a property of the data, not of the rule.

### 44.1 Six instances

The class was named after three. A directed sweep of 20 predicates across
`resolver/` and `corpus/oracle.py` found two more, and one of the two is in
the **oracle** — the component that scores everything else. A sixth surfaced
later, outside that sweep, in code none of this project's passes had reason
to look at.

| # | where | left side | right side | claim it inflated |
|---|---|---|---|---|
| §39 | `enumerate_closures.py` | **external** wall clock | CP-SAT's **internal** limit | a truncated enumeration recorded as exhaustive; `Reconstructed` requires closure *proven complete*, so a truncated set of size one could have been promoted |
| §41 | `breaks.py` (was `resolve.py`) | refunds vs **fee-net** `credit` | frozen simulator's **gross** `amount` | an over-refunded or ₹1-short payment read as fully netted; 8 rows claimed as never-settled had settled |
| D13 | `breaks.py` break reason | `on_hold` **current-state snapshot** | the **past** settlement horizon | 202 of 540 disputed rows (37.4%) disagree between the two |
| **F1** | `eligibility.py:73` | the **same** snapshot | the **same** past horizon | the pool's stated **superset** invariant, silently broken |
| **F2** | `oracle.py:219, 551` | uniqueness over the **true** pool | a resolver searching a **derived** pool 1.4×–14× larger | "the benchmark proves this line has exactly one explanation" |
| **§49** | `matching/stage3_solver.py` (frozen, `81c04e0`) | **external** wall clock | CP-SAT's **internal** limit | two runs of the same frozen baseline disagreeing on 10 of 30 datasets — the same shape as §39, in the code §39's fix was never applied to |

F1 and D13 are *the same error, one file apart*. Cataloguing D13 did not
prevent F1, and F1 was written after D13 was known — which is the point of
§44.4. §49 is the same pair again, at a further remove: it is §39's own
error, in the codebase §39's author was actively comparing against.

### 44.2 What each instance cost

**§39** and **§41** were soundness hazards and are fixed. **D13** is bounded
by an API ceiling and is open (44.5). **F1** is fixed in the cycle that
follows this entry; it never bit, which is exactly why it needed fixing —
see §45. **F2** is a *corpus* defect and the gate is **not** loosened for it;
only every statement of a G8 result is rescoped (§46). **§49** was a
reproducibility hazard rather than a correctness one — every run computed a
CP-SAT-valid answer, just not the same one twice — and is fixed; the before/after pair and the
reconciliation against everything previously published from the old baseline
are in §49 itself.

### 44.3 A mixed-frame computation survived one line above the fix that removed it

`enumerate_closures.py:98` still computes `timed_out` from an externally
measured `elapsed` against an internal solver status — one line above line
119, where §39 replaced exactly that mixture with `status == OPTIMAL`. It
feeds only the reported status *label* and can never reach `complete`, so it
is not a soundness hazard, and it is deliberately left in place with a comment
saying so rather than quietly tidied.

It is recorded because **that is how these hide**: the fix was correct, the
review that accepted it was looking at the right function, and the same
mixture eighteen characters up was not seen by anyone, including the author of
the fix.

### 44.4 The meta-observation, recorded plainly

The sweep was run by someone who had just finished cataloguing three instances
of this exact class and was explicitly looking for a fourth. **It found two
more, and the more serious of the two was in the scorer.**

This is the same result `corpus/leakage_audit.py` produced on the corpus, in a
different coordinate: a directed search by an informed searcher still finds
things, which means the informed searcher was not the control. It says the
same thing both times — **this class is not eliminable by care, only by
mechanism.** Care found five; nothing establishes there is not a sixth.

The mechanism the rule in this entry asks for — frames named in code — is
weaker than a checker that verifies them, and no such checker exists here.
That is a named gap, not a solved problem.

#### Five times, now, and the fourth and fifth both change the moral

This is no longer a coincidence and is recorded as a count:

1. **§39 — the `complete` flag.** A claim of a stronger epistemic state than
   was measured, *inside the resolver written to prevent exactly that*.
2. **`CLAIMS.md`'s own denominator error.** The ledger built to make every
   number carry its denominator reported 14 abstentions on determined
   instances by computing `instances − resolved`; those 14 are
   `AttestationDiscrepancy` — findings, not silences — and the gate's count is
   0. It failed on its **first execution**.
3. **§48 — the coverage metric.** Introduced *by the reporting-honesty pass
   whose entire purpose was to remove this class of error*, and it fell as
   detection improved.
4. **§49 — `max_time_in_seconds` in the frozen cascade.** Unlike the first
   three, this one was **not written by this project's process at all**. It
   predates the phase entirely — `matching/stage3_solver.py` is frozen at
   `81c04e0`, authored to be replaced, not audited — and no pass of this
   project's own work could have caught it, because no pass of this project's
   own work ever looked at it. It was recognizable only because §39's fix
   *created the vocabulary to see it*: "an externally measured clock compared
   against CP-SAT's internal state" was not a category that existed here
   before §39, and once it did, it applied to code this project did not
   write just as much as to code it did.
5. **§50 — `truncated` computed from the cap alone, one function deeper than
   §49.** Found *while fixing §49*, in the same frozen function, and
   deliberately deferred to its own cycle rather than patched inline. Its
   own committed prediction (0–5 enumerations flip, no `Determinate`
   decreases) **missed badly** — at least 26 flipped, and **three
   previously-published `Determinate` results in the frozen-cascade
   comparison were never actually proven unique**
   (`datasets_v2/A20_B100_Cfifo`, `datasets_v2/A40_B100_Cfifo`,
   `datasets_v2/A40_B100_Cmax`; full accounting in
   `investigation/nondeterminism_evidence/TRUNCATED_RESULTS.md`). This
   repository's own `THREE_SYSTEMS.md` carried an overstated soundness claim
   about the frozen cascade — the comparison's *baseline*, not its subject —
   for exactly as long as §49 was fixed and §50 was not, and that period is
   now closed and dated.

The first three were written by someone who had just finished cataloguing the
previous one, and that is the story the first three instances tell on their
own: **the author of a rule is the worst available auditor of their own
compliance with it**, because the same misunderstanding that produced the
error also produces the check for it. The fourth and fifth instances do not
fit that story — nobody here wrote `matching/stage3_solver.py`'s clock or its
enumeration-cap check — and together they revise the moral rather than merely
extending the count twice: **sometimes the mechanism that catches an old
defect is a newer defect's own postmortem, and once that mechanism exists it
does not stop at the first thing it finds.** Fixing §39 left behind a
description precise enough to recognize the same shape in code this project
never wrote (§49); fixing §49 then put a reviewer's attention directly on the
one function most likely to hold a sibling defect, and it did (§50). Neither
is self-congratulation — the fifth instance is evidence that finding one
frozen-code defect via this mechanism does not exhaust the function it was
found in, not evidence that the search is now thorough.

What caught all five was a *mechanism* — a gate, a generated table, a
diagnostic that recomputed a number from a different direction, a fix whose
own vocabulary generalized past its original target, a deliberate deferral
followed by a second pass over the same code — and in each case the mechanism
was built for a different purpose and caught this as a side effect.

The honest implication is uncomfortable and is stated rather than softened:
**there is no reason to believe there is not a sixth.** The controls that
exist are the ones that found these five, and none of them was designed to.

#### 44.10 A truncated field that did not announce its truncation

`corpus/score_resolver.py` wrote `report.violations[:12]` into
`oracle_results.json` with nothing recording that the list was a sample. At
`datasets/A20_Bnone_Cmax` it stored 3 `G8` entries while `violations_by_gate`
correctly recorded 9.

**No published figure was affected.** Every gate number in this repository
derives from `violations_by_gate`, which was always complete, and
`test_the_gate_counts_are_complete_even_when_the_sample_is_not` now asserts
that. This is a reporting truncation, not a soundness defect, and describing
it as anything more would cost the same credibility as hiding it.

Fixed anyway: the field now carries `violations_total` and
`violations_truncated`. Found while reconciling two fields that disagreed —
not by looking for it.

**A second instance surfaced the moment a static guard existed for the
first:** `corpus/baseline_old_engine.py` capped three `detail` lists at 8 with
no flag. Same class, same absence of impact — the counts beside them were
always complete — and it was found by a test written for a different file, one
minute after that test existed.

### 44.5 D13's ceiling is the API, not the algorithm

Razorpay's dispute entity publishes `id`, `entity`, `payment_id`, `amount`,
`currency`, `amount_deducted`, `reason_code`, `reason_description`,
`respond_by`, `status`, `phase`, `created_at`, `evidence`. There is **no
resolution timestamp of any kind** — no won/lost/closed date, no hold-release
field — and `status` is a current-state scalar.

So `created_at` makes *"the hold had not begun at the horizon"* computable,
and nothing makes *"the hold was released before the horizon"* computable.
That is a bound on **any** resolver consuming this feed, not a gap in this
one, which is the stronger and more useful statement.

Two incidental corpus gaps found while checking: the corpus models 3 of the 5
documented phases (`pre_arbitration` and `arbitration` are absent — a won
chargeback re-challenged, which is precisely the retroactive case §37 is
about) and 3 of the 5 documented statuses (`open` and `closed` absent).

### 44.6 Rejected alternatives

**Rejected: fix F2 by loosening G8.** Loosening a gate after watching a
resolver fail it is the move the freeze discipline exists to forbid, and G8
exists precisely because abstention is otherwise free. It keeps failing, and
what changes is the *claim*, not the threshold.

**Rejected: leave F1 alone because it measures 0 rows affected.** That is the
D2 argument verbatim — a branch whose safety came from the data, inside a
passing suite, right up until held-out data moved 50 rows.

**Rejected: fold the `timed_out` mixture into the enum while I am here.**
Tidying it destroys the evidence in §44.3, which is the most instructive part
of this entry.

**Rejected: treat "five instances found, class understood" as closure.** The
count is the argument in the other direction. See §44.4.

### 44.8 A narrower class inside this one: uniqueness is relative to a search space

Three of the five instances above are a **sharper** class than §44's, and the
F1 result named it without generalising it:

| | the uniqueness claim | the space it was actually true over |
|---|---|---|
| §39 | "this enumeration is complete, so the closure is unique" | a space CP-SAT **had not finished searching** |
| F1 | `Reconstructed` — exactly one closing subset | a pool **missing every held row** |
| F2 | `ReconstructibleInstance` — exactly one closing subset | the **simulator's** pool, 1.4×–14× smaller than the resolver's |

F1 is the clearest statement of it, and it generalises the other two:

> **A pool that is too small hides rivals, and a hidden rival is
> indistinguishable from no rival.**

`datasets/A20_B50_Cmax` is the demonstration. Its wrong `Reconstructed` was
not produced by bad arithmetic — the arithmetic was exact and the closure
genuinely was unique *over the pool it was given*. Restoring the held rows
produced a rival that had been there all along, and the outcome fell to
`Ambiguous`. Nothing about the world changed; the search space did.

**Therefore: uniqueness is only meaningful relative to a stated search space,
and every claim of uniqueness must name the space it is unique over.**

This is not a new decision. It is what §44's rule already requires — a
predicate must name its frame — applied to the particular frame that is a
*set of candidates* rather than a clock or a quantity. It is written down
separately because "which pool" is much easier to leave unstated than "which
clock", and three of five instances went that way.

#### Where each uniqueness claim in this repository states its space

Recorded as findings. **None of these is changed in this task.**

| claim | space it is unique over | stated? |
|---|---|---|
| `Verified.rival_closure_count` | "closing subsets of **the pool at this line**" (`types.py`) | **partially.** It names *a* pool but not *whose*: the resolver's derived pool, not the simulator's. `rival_count_is_lower_bound` correctly covers the truncation case (§39), so only the pool-identity half is missing |
| `Reconstructed` | contract §4.3 requires the **window** for cross-line exclusivity to be stated on the evidence's `detail` | **the window is required; the POOL is not.** §4.3 says "the pool admitted exactly one closing subset" without saying which pool, and after F1 that is precisely the gap that mattered |
| `Ambiguous` / `CandidateSet` | carries `complete` and `enumeration_cap` | **the completeness of the search is stated; the extent of the pool is not** |
| `DeterminedInstance` | "exactly one subset of **the pool** closes to the credit" — the **simulator's** pool | **not stated as the simulator's.** The reader cannot tell it is not the resolver's |
| `ReconstructibleInstance` | same — the simulator's pool | **not stated.** This is D15, and it is why both remaining oracle failures rest on a premise the resolver cannot be held to (§46) |

The pattern in that table is the finding: **every one of these states how
thoroughly the space was searched, and none of them states how large the space
was.** Completeness was treated as the whole of the question. It is half.

### 44.9 Appendix — the full 20-predicate inventory

Every predicate comparing two quantities in `resolver/` and
`corpus/oracle.py`. Reported in full, failures and passes alike: **a clean
sweep is evidence only if it was exhaustive.**

| # | predicate | left frame | right frame | verdict |
|---|---|---|---|---|
| 1 | `breaks.py:81` `Σrefund.debit == row["amount"]` | PSP gross | PSP gross | ✅ (§41 fix) |
| 2 | `breaks.py:82` `refund.created_at <= eligible_at` | PSP ledger | PSP-derived | ✅ |
| 3 | `breaks.py:90` `row["credit"] == 0` | PSP | literal | ✅ |
| 4 | `breaks.py:155` `first_reconcilable > end_of_day(horizon)` | PSP-derived | **bank** | ⚠️ D14 — sound in one direction only, guarded by the horizon test in `resolver/tests/test_pool_frame.py` |
| 5 | `breaks.py:160` `dispute is not None or on_hold` | snapshot | — | ⚠️ **safe by construction** — feeds `OpenBreak`, which asserts nothing (§40) |
| 6 | `eligibility.py:73` `row.get("on_hold")` | **snapshot** | **as-at past `value_date`** | ❌ **F1**, fixed in §45 |
| 7 | `eligibility.py:75, 80` `created_at / eligible_at > ceiling` | PSP | bank end-of-day | ⚠️ errs LARGE, stated in the docstring |
| 8 | `eligibility.py:82` `net(row) == 0` | PSP net | literal | ✅ |
| 9 | `enumerate_closures.py:98` `elapsed >= time_budget` | **external clock** | **internal status** | ⚠️ **F3**, label-only, retained deliberately (§44.3) |
| 10 | `enumerate_closures.py:119` `complete = status == OPTIMAL` | internal | internal | ✅ (§39 fix) |
| 11 | `resolve.py:189–191` reversal window | bank | bank | ✅ |
| 12 | `resolve.py:479` `reported_amount != line.amount_paise` | PSP payout | bank payout | ✅ verified the same quantity |
| 13 | `resolve.py:493` `attested_net != line.amount_paise` | PSP fee-net | bank payout | ✅ both fee-net |
| 14 | `resolve.py:512, 601` `created_at > ceiling` | PSP | bank | ⚠️ deliberate cross-party check; the contradiction IS the finding |
| 15 | `resolve.py:566` `Σnet == line.amount_paise` | PSP fee-net | bank | ✅ |
| 16 | `resolve.py:673` rival amounts | bank | bank | ✅ |
| 17 | `loaders.py:36` `amount_paise > 0` | bank | literal | ✅ |
| 18 | `oracle.py:219` `recoverable != "unique"` | corpus register, **true** pool | resolver search, **derived** pool | ❌ **F2**, §46 |
| 19 | `oracle.py:551` `register["count"] < 2` | as #18 | as #18 | ❌ same root |
| 20 | `oracle.py:279, 341, 406, 459` composition / candidate equality | truth | resolver | ✅ |

---

## 45. F1 is fixed although it bites nothing, and the fix removed the resolver's only wrong answer

**Decision.** `resolver/eligibility.py` no longer drops a row from the pool for
carrying `on_hold`. Prediction committed in `427aea6`, fix in `4b65764`,
scored once. `investigation/F1_PREDICTION.md` carries both.

**Why, given 0 rows were affected.** The measurement *is* the argument: 0 rows
carrying `on_hold` appear in any true composition across 30 datasets, so the
filter was correct here by a property of the generated data rather than of the
rule. `investigation/DEFECT_REPORT.md` records D2 as exactly that shape — a
branch whose safety came from the data, inside a passing suite, until held-out
data moved 50 rows. And `pool_at`'s own docstring promises a **superset** and
says the module "errs LARGE where the rules are uncertain"; this filter erred
small, which is the silent direction.

**What it cost: nothing measurable, and it removed a wrong answer.** G3, G8,
G9, `Verified` and `Unresolved` are identical across the two runs. Mean pool
growth +1.7%. The `Reconstructed` at `datasets/A20_B50_Cmax` — an adoption of
a bank line that is not a settlement of ours, and the resolver's **only wrong
answer** — acquired a rival closing subset once the held rows were restored,
and fell to `Ambiguous`. **A pool that is too small hides rivals, and a hidden
rival is indistinguishable from no rival.** Not predicted, one instance, and
`Reconstructed` occurs once in the whole corpus, so it is reported as a count
and not as a rate.

**The prediction was wrong in one line, and the error is instructive.** It
asserted `ProvenUnmatched` would be "699 exactly" because rows returning from
a destroyed `Reconstructed` "settled, so they cannot become
`ProvenUnmatched`". That clause assumed the assignment being destroyed was a
*true* one. It was the false one, its rows never settled, and two are entailed.
Actual: 701.

**Rejected: guard the filter instead of removing it.** A guard on a snapshot
read against a past horizon is still a snapshot read against a past horizon.

**Rejected: keep the filter and rely on the corpus-wide superset test.** That
test passes *with the filter present*, because no corpus row exercises the
case. It is retained as a regression guard and its docstring says plainly that
it did not catch F1 and would not have. The discriminating test is synthetic.

---

## 46. G8's premise is scoped to a pool no resolver can see, and the gate is not loosened

**Decision.** `corpus/oracle.py`'s G8 stays exactly as it is. What changes is
**every statement of a G8 result**, which must now carry its pool scope inline.

**The finding.** `corpus/generator/build.py:853` builds the closure register
over *"the EXACT pool the rule was applied to, recorded by the simulator"* —
and the comment continues, correctly, *"a register built over a RECONSTRUCTED
pool measures the reconstruction, not the truth."* That is right for its
purpose. G8 then uses `ReconstructibleInstance` to call a resolver's
abstention a **defect**, while the resolver searches a pool it derived itself:

| dataset | line | true pool | resolver pool | ratio |
|---|---:|---:|---:|---:|
| `A20_Bnone_Cmax` | 16 | 15 | **213** | 14.2× |
| `A20_Bnone_Cmax` | 18 | 23 | **265** | 11.5× |
| `A40_Bnone_Cmax` | 15 | 38 | **414** | 10.9× |

All 18 reconstructible instances at the absence points, and therefore all 15
G8 failures across both FAILing datasets, rest on this. **Uniqueness in 2¹⁵ is
not evidence of uniqueness in 2²¹³.**

So the README's *"abstained on 15 of 18 bank lines the benchmark proves have
exactly one explanation"* was **false as written**. The benchmark proves
uniqueness over a pool no merchant-side resolver can know.

**Rejected: loosen G8.** Loosening a gate after watching a resolver fail it is
the move the freeze discipline exists to forbid, and G8 exists precisely
because abstention is otherwise free. It keeps failing. The *claim* changes,
not the threshold.

**Rejected: rebuild the register over a reconstructed pool.** That destroys the
property the register was built for — it would measure the reconstruction
rather than the truth — and it would mean regenerating frozen datasets.

**The measurement that would settle it, named and NOT taken:** the closure
count over the **derived** pool at those 18 lines. If it is 1, the abstentions
are genuine failures; if it is large, they are correct refusals and G8 is
measuring the wrong thing. It is unmeasured. Measuring it is new apparatus and
is out of scope here.

**This is CHECKPOINT §12.4 seen from the other end.** Contract §2.4 gives
consumption to `Verified` alone; at PSP absence nothing attests, so nothing
consumes, so the pool grows monotonically to ~10× the true pool, so uniqueness
over the true pool is not a fair bar. **The gate and the open consumption
problem are one problem**, and fixing either requires the other.

---

## 47. Inference from an unverified premise: a claim already written down is still a premise

**The class.** An inference whose soundness silently depends on a premise
**nobody checked**, where the premise looked sound because it was *already
written down in this repository*. Being recorded is not evidence. Two
instances, both previously logged, neither previously connected.

**§31 — a theorem asserted, gated on, never measured.** Contract §6.3 asserted
that at 0% attestation coverage `Verified` is provably empty, and gate G5
enforced it. The theorem was false on the corpus's own data. The prediction
"`|Verified| = 0`" came true for a different reason, so nothing was learned
from its coming true, and G5 would have rejected correct answers. Both §6.3
and G5 are withdrawn.

**§45 — a prediction that inherited a false claim's correctness.** The F1
prediction argued `ProvenUnmatched` could not move, because rows returning
from a destroyed `Reconstructed` "settled, so they cannot become
`ProvenUnmatched`". The clause assumed the assignment being destroyed was a
**true** one. It was the resolver's only *wrong* answer; its rows had never
settled and two are entailed. Predicted 699, actual 701.

**The rule.**

> When a prediction, a gate, or an argument rests on an existing claim in this
> repository, that claim is a **premise to be checked**, not a fact to be
> cited. Write down which claim you are leaning on and how you verified it —
> or state that you did not, and treat the conclusion as conditional.

**Why it is worth naming at two instances.** The failure mode is invisible in
review, because the citation is *correct*: §6.3 really did say that, and the
`Reconstructed` really did exist. What is missing is the step where somebody
asks whether the thing being cited is true. This repository generates its
numbers precisely so that claims can be re-derived rather than remembered —
and both instances are cases of leaning on a claim without re-deriving it, in
a project whose entire discipline is not doing that.

**Related but distinct from §44.** §44 is about a predicate comparing two
things measured in different frames. This is about an argument resting on a
conclusion nobody re-checked. They share a symptom — a claim stronger than the
evidence supports — and differ in mechanism.

**Rejected: adding a checklist step to the prediction protocol.** The
prediction protocol already works; §45's prediction was wrong in one line out
of six and the error was visible *immediately* on scoring, which is what the
protocol is for. A checklist would not have caught it, because the author
believed the premise. What catches it is committing the prediction with its
reasoning **written out**, so the false step is legible afterwards — which is
what happened, and why §45 could name the exact clause that failed.

---

## 48. Coverage is reported three ways, because a line the resolver MUST NOT answer is not a line it failed to answer

**Decision.** The single figure `coverage = (Verified + Reconstructed) /
settlement lines` is replaced everywhere by a three-way split plus one derived
rate, computed once in `corpus/coverage.py` and shared by every report:

| | |
|---|---|
| **answered** | `Verified` / `Reconstructed` — a composition claim was made |
| **not determinable** | `Unresolved` / `Ambiguous` — the resolver could not |
| **record contradicted** | `AttestationDiscrepancy` — the resolver **must not**; contract §4.2 forbids asserting a composition the record contradicts |
| **coverage on determinable lines** | `answered / (answered + not determinable)` |

Every published figure names one of the four scopes in `coverage.SCOPES`.

**The defect.** The single figure collapsed the second and third categories,
so it **fell as detection improved**. Measured: `datasets_v2` plants one false
`settlement_id` per dataset, the resolver catches **13 of 13**, and its
coverage drops from 85% to 79% *because it caught them*. On the 28 datasets
carrying a PSP artefact, **all 60 unattempted lines are `record contradicted`,
and all 62 discrepancy findings in the corpus are correct — 0 genuinely
false** (`investigation/D15_MEASUREMENT.md` §1).

A metric that penalises a reconciliation engine for detecting record errors is
not a conservative metric. It is a wrong one, and it happens to point in the
flattering direction *for the benchmark* rather than for the engine, which is
why nobody caught it by reading.

**Rejected: keep one number and explain it in prose.** This is the option that
was in effect, and it failed. The caveat existed — `THREE_SYSTEMS.md` carried a
sentence about declined lines — and a reader skimming the table saw "85%" and
"79%" and drew the obvious wrong inference. **Prose does not survive a skim**,
and the entire purpose of the reporting pass (§14.3) was to stop relying on it.

**Rejected: report only `answered / determinable` and drop the rest.** It reads
as 100% on the non-absence datasets, which is true and would be quoted without
the fact that 60 lines were excluded from the denominator. A rate whose
denominator excludes something interesting must show what it excluded.

**Rejected: count `record contradicted` as answered.** It is the opposite
error. The resolver made no composition claim on those lines, deliberately,
and counting a refusal as an answer is how `Determinate` came to mean four
different things.

**How it was found.** Not by review. The D15 diagnostic decomposed coverage in
order to locate 25 unattempted lines, and the decomposition showed that 60 of
60 on the non-absence datasets were correct findings. The metric was introduced
by the pass that existed to remove this class of error; see §44.4, where it is
recorded as the third such instance.

---

## 49. `max_deterministic_time`, not `max_time_in_seconds` — §39's class, found one component over, in code this project did not write

**The defect.** `matching/stage3_solver.py` — the frozen cascade, `81c04e0`,
the engine this project was built to replace — sets
`solver.parameters.max_time_in_seconds = 30.0` at both of its CP-SAT solve
calls. That is a **wall-clock** budget: identical search orders
(`num_workers=1`, so the order is otherwise reproducible) run for 30 seconds
of real time regardless of how much CPU contention exists during that window,
so the same dataset produces a different truncation point — and therefore a
different outcome distribution — depending on what else the machine was doing.
This is `DECISIONS.md` §39's exact class (`enumerate_closures.py`'s external
wall clock compared against CP-SAT's internal state), found **one component
over**: not in the resolver §39 already fixed, but in the frozen cascade the
resolver exists to be compared against.

**How it was found.** Not by review, and not by looking for it. `corpus/
baseline_old_engine.py --all` was run twice in the course of ordinary work on
this phase — once alone, once with an oracle-scoring pass running
concurrently — and the two runs disagreed on 10 of 30 datasets'
`Determinate`/`Ambiguous`/`Unresolved` counts. `investigation/FINAL_GATE.md`
diagnosed the mechanism before this decision was written.

**The fix.** `max_time_in_seconds` → `max_deterministic_time` at both call
sites, keeping the same numeric value (30.0) as the simplest choice that
preserves the budget's order of magnitude without a theoretical claim that it
is an equivalent *amount* of search — OR-Tools does not publish a fixed
conversion between deterministic-time units and wall-clock seconds by design.
`investigation/nondeterminism_evidence/PREDICTION.md` states this reasoning
in full, committed before the fix existed.

**The contended-run verification, not skipped.** A directional prediction
(weak, explicitly flagged as resting on an unverified premise — the exact §47
shape) was committed before the fix. The result: **the prediction is not
confirmed.** Of the 10 disagreeing datasets, the stable output matches the
prior run A on 2, matches prior run B on 2, and matches **neither** on 6 — four
of those six are cases where A and B had *agreed with each other* and the
deterministic-budget result broke with both. Full accounting:
`investigation/nondeterminism_evidence/RECONCILIATION.md`. Determinism itself
is confirmed separately and unconditionally: three uncontended runs of
`corpus/baseline_old_engine.py --all` are byte-identical excluding wall-clock
`seconds`, and a fourth run — deliberately contended with a concurrent
`corpus/score_resolver.py --all` — matches all three exactly.

**The before/after pair, published rather than discarded**, per the §39
standard: `corpus/baseline_results_predeterminism.json` (the old,
uncontrolled draw — bit-identical to the run committed in
`corpus/baseline_results.json` before this fix) and `corpus/
baseline_results.json` (now the verified-stable run). Every downstream figure
sourced from the old file — `corpus/THREE_SYSTEMS.md`, `README.md`,
`CHECKPOINT.md` §4.6 — is recomputed, not eyeballed for closeness; see
`RECONCILIATION.md` for the dataset-by-dataset diff. `CLAIMS.md` and
`SCORECARD.md` were checked and are unaffected: `SCORECARD.md` never reads
`baseline_results.json`, and `CLAIMS.md`'s only use of it (`len(ran)` of 30
datasets) does not change.

**Rejected: leave `max_time_in_seconds` alone because the frozen cascade is
already documented as defective.** `investigation/DEFECT_REPORT.md`'s three
defects (D1–D3) are about what the cascade computes; this is about whether two
runs of the same computation agree with each other at all, which is a
precondition for every comparison in `corpus/THREE_SYSTEMS.md` and
`corpus/BASELINE_OLD_ENGINE.md`, not a fourth item on that list. A frozen
baseline that is not reproducible is not a baseline.

**Scope, held exactly.** Only the two `max_time_in_seconds` call sites and
their immediate consequence (`over_time_budget`'s derivation, forced by the
same edit — see §44.3's precedent for a mixed-frame line surviving one line
above a fix) changed in `matching/`. `num_workers`, the objective, and
`ENUMERATION_CAP` are untouched. `engine/`, `resolver/`, `resolver_contract/`,
and `corpus/oracle.py` are untouched. A second, adjacent defect in the same
function — `truncated` computed from the enumeration cap alone, never from
solver status — was found and deliberately left for its own cycle; see §50.

**Distinct from §44's other four instances, and worth stating precisely: this
one was not written by this project's process.** `matching/stage3_solver.py`
is frozen at `81c04e0`, predates this phase, and was authored to be *replaced*
by the resolver, not audited by it. It became visible only because §39's fix
gave this project the vocabulary — "an externally measured clock compared
against CP-SAT's internal state is a defect" — to recognize the same shape in
someone else's code. See §44.4's fourth instance for the moral this changes.

---

## 50. `truncated` must reflect the enumerator's own status, not the cap alone — §39's class, third time, one function deeper than §49

**The defect.** `matching/stage3_solver.py:enumerate_decompositions` computed
`truncated = hit_cap` (`len(collector.subsets) >= cap`) and separately derived
`over_time_budget` from the enumerator's own CP-SAT status, without folding
the second into the first. An enumeration that exhausted its
deterministic-time budget **before** reaching the cap was therefore reported
`truncated=False` — a stopped-early search recorded as a completed one.
`matching/model.py:resolve_from_candidates` branches on `truncated` directly:
`len(unique) == 1 and not truncated` returns `Determinate`, a claim of proven
uniqueness. A line where the budget ran out after finding exactly one
candidate, without ruling out a second, was indistinguishable from a line
genuinely proven unique.

**How it was found.** Found and deliberately left alone while fixing §49, in
the same function, because §49's authorized scope was the wall-clock →
deterministic-time swap and nothing else. Recorded as a follow-on finding at
the time; fixed now, in its own cycle, per that plan.

**The fix.** `truncated = enum_status != cp_model.OPTIMAL`, replacing
`hit_cap` alone. A `StopSearch()` call at the cap reports `FEASIBLE`, never
`OPTIMAL`, exactly as a budget-exhausted stop does — so this single
expression covers both cap-hit and budget-exhaustion, which is the point:
they are both truncation.

**The prediction, and the miss.** `investigation/nondeterminism_evidence/
TRUNCATED_PREDICTION.md`, committed before the fix, reasoned from
`ENUMERATION_CAP = 32` and the corpus's observed candidate counts that few
enumerations (0–5) would flip, and that no `Determinate` count would
decrease. **Both claims missed, and by a wide margin.**
`unrepresentable_claims` fell in 16 of 30 datasets by 26 in total — a lower
bound on the true flip count, since a flip on an `Unresolved` outcome or an
already-empty `certain_rows` produces no visible signal in that field at all.
**Three `Determinate` results decreased**:
`datasets_v2/A20_B100_Cfifo` (4→3), `datasets_v2/A40_B100_Cfifo` (3→2),
`datasets_v2/A40_B100_Cmax` (3→2). Three lines previously published as
`Determinate` in the frozen-cascade baseline had never actually been proven
unique — the search that produced them was cut off by the deterministic-time
budget, not exhausted. Full accounting: `investigation/
nondeterminism_evidence/TRUNCATED_RESULTS.md`.

**Why the prediction's reasoning was wrong, stated plainly.** It conflated
the cost of *finding* solutions with the cost of *proving no more exist*.
CP-SAT can find every actual solution to a subset-sum instance quickly and
still spend a large amount of deterministic time exhausting the remaining
branches to confirm completeness; that proof cost is a property of the
pool's size and structure, not of how many solutions were found. "Few
solutions found" was treated as evidence of "little search needed," and that
inference does not hold for exhaustive enumeration. This is itself a useful,
if humbling, calibration of `SOLVER_TIME_LIMIT_SECONDS = 30.0`: it is
adequate for many pools in this corpus but not all, and the pools it is
inadequate for are not identifiable in advance from candidate-set size alone.

**The before/after pair.** `corpus/baseline_results_pretruncationfix.json`
(the run with §49's fix but this section's bug still present) and
`corpus/baseline_results.json` (now this fix's output). A second pair
alongside §49's, both preserved rather than discarded.

**Downstream figures, recomputed again.** `corpus/THREE_SYSTEMS.md`,
README.md's spliced summary, and `CHECKPOINT.md` §4.6 (a second, dated
correction: unrepresentable claims on the original-14 family fall further,
59 → 46; outcome buckets on that family do not move again, since all three
`Determinate` flips are in `datasets_v2`). `CLAIMS.md` checked, unaffected.

**Scope, held exactly.** Only `enumerate_decompositions`'s `truncated`
computation changed. `num_workers`, the objective, `ENUMERATION_CAP`, and
everything §49 already fixed are untouched.

**§44.9's inventory, updated.** This is the reference-frame class's *third*
instance inside one function — §39's `complete` flag was the resolver-side
original; §49 found the same shape in the frozen cascade's clock; this is a
second, independent predicate in that same frozen-cascade function computing
"did the search finish" from an incomplete signal. Three instances, in one
function, found across three separate passes, is itself evidence for §44.4's
claim that this class is not eliminable by care: each pass fixed what it was
looking at and left the adjacent line for the next one to find.

---

## 51. A wrong-*bank*-side class is added, scoped to `mispost` only, and scored outside the 30-dataset aggregate

**Decision.** A new planted class corrupts the **bank** side of a settlement
rather than the PSP's attestation: one bank credit's amount is replaced with
an amount that matches no valid batch composition, while
`settlement_report.csv` and `recon_combined.json` are left correct and
untouched. It lands in a new module, `corpus/generator/bank_side_errors.py`,
called from `build.py` on the `payouts` sequence *before*
`build_bank_statement` runs — `bank.py` itself is not edited, so the
independence guarantee its `Payout` signature encodes (amount + timestamp,
nothing else) is exercised, not weakened. Two new datasets, one axis point
each, ship in a new family, `corpus/datasets_bankside/`.

**Why.** README's own Limitations section names this the largest remaining
gap: every planted record error so far corrupts the PSP's attestation; the
benchmark never once tests the direction where the bank side disagrees and is
the one that is wrong. `AttestationDiscrepancy`'s own contract text is
already symmetric — "the sources disagree… a finding about the record, not a
claim about which rows settled" — so this class asks whether that symmetry
holds in the implementation, not just in the prose.

**Scoped to `mispost`, not `split-credit`.** A second shape was considered —
one settlement posted as two separate bank credits summing to the true
amount. It was set aside for this pass: it may expose a real question the
outcome vocabulary does not yet answer (can any current outcome represent
"these two bank lines are jointly one attested settlement"?), and this
project's own rule is that a change to `resolver_contract` is a dated,
separate decision (§31, §46), never folded into corpus work that happens to
provoke it. If the resolver mishandles `split-credit` when it is eventually
built, that is a finding to write up, not a reason to extend the contract in
the same change that discovered it.

**Rejected: fold the new family into `FAMILIES`/`three_systems.py`.**
`corpus/three_systems.py`, `corpus/scorecard.py`, and `corpus/claims_ledger.py`
carry the dataset counts as narrative prose — "30 datasets", "the 28
datasets" — not purely computed values. Adding a two-dataset family whose
main purpose is exposing a gap, not producing a new headline aggregate,
would mean editing sentences inside three already-cited, already-audited
generated documents for a small addition. Rejected in favor of a dedicated,
small scorer, `corpus/score_bankside.py`, writing `corpus/BANKSIDE_RESULTS.md`
and `.json`. The existing cited numbers stay true and stable.

**A finding, made while implementing this decision rather than assumed in
advance.** `corpus/leakage_audit.py` and `corpus/triviality_check.py` are
class-agnostic — both read `ground_truth.json["planted_classes"]` and
per-dataset directory contents generically, so a `table: "bank"` planted
class needs no change to either script's *auditing* logic, and
`leakage_audit.py`'s `load_tables` already builds a `bank` table keyed by
`_file_position` (the bank statement's line index), which is exactly the key
a bank-side planted class needs. But both scripts' `--all` convenience flag
hardcodes `FAMILIES = ("datasets", "datasets_v2")` (identically, in both
files) to discover what to audit — a new family is invisible to `--all`
until that tuple is extended. `datasets_bankside` is added to both tuples.
This is corpus-tooling code, not `resolver/` or `matching/`, so extending it
is within this pass's scope; it is recorded here because the original plan
for this class assumed `--all` would need no changes, and that assumption
was wrong.

---

## 52. The adversarial-input suite fails the build only on a silently wrong answer, never on a raised exception

**Decision.** `tests/adversarial/` feeds `resolver/` and `matching/` — read
only, through their existing public `load()`/`resolve()`/`run_cascade()`
entry points — a family of single-field corruptions of an otherwise-valid
dataset: negative amounts, duplicate `settlement_id`/`bank_reference`,
truncated or malformed JSON, out-of-order timestamps, over-precision decimal
strings, missing optional files, empty files, non-numeric fields. Every case
is sorted into exactly one of three buckets: (1) a clean, typed decline —
best; (2) an uncaught low-level exception (`KeyError`, `ValueError`, …) —
acceptable, but named and cataloged so a change in which exception fires is
visible; (3) a **silent, plausible-looking wrong answer** — a `Verified` or
equivalent built from corrupted input with no signal anything was off. Only
bucket 3 fails the suite.

**Why.** This suite lives outside `corpus/` because it is not a claim about
composition accuracy and must never be read as one — it answers "does this
degrade safely," not "is this correct," and mixing the two is exactly the
error `eval/scale_report.py` was already written to avoid for throughput
numbers. Bucket 3 is the only outcome that matters for a financial system: an
uncaught `KeyError` on a truncated CSV is safe (nothing downstream trusts a
crash), a clean decline is the contract working as designed, but a resolver
that turns a corrupted input into a confident, wrong `Verified` is the one
failure mode with no downstream backstop.

**Rejected: fail on any uncaught exception.** Would implicitly demand
hardening `resolver/`/`matching/` against every malformed-input case this
pass enumerates — that is resolver work, and this pass's hard constraint is
that corpus/test work and resolver code changes do not land in the same
change. A defect the suite finds gets written up alongside
`investigation/DEFECT_REPORT.md`'s existing three, not patched here.

**Rejected: gate through `corpus/oracle.py`'s G1–G9 machinery.** Those gates
score `(resolver_output, ground_truth)` pairs from the seeded corpus; this
suite has no ground truth to score against — a corrupted input by
construction closes to nothing, or to something arbitrary. It needs its own
three-bucket accounting, not a new oracle gate.

---

## 53. `scale/` is run to completion for the frozen cascade only; measuring the resolver at scale is deferred, not attempted

**Decision.** `scale/generate_scale.py` and `eval/scale_report.py` are run
as they already exist, unmodified, producing the long-missing
`scale/SCALE_REPORT.md`. No new code is written to point either script at
`resolver/`.

**Why deferred, not built.** `scale/`'s fixtures are frozen-generator CSV
shape, read by `matching.loaders.load`; `resolver/loaders.py` reads only the
corpus-generator JSON shape (`recon_combined.json`), produced solely by
`corpus/generator/build.py`. There is no flag or adapter that makes the
existing fixtures legible to the resolver — measuring it at scale means
generating **new**, larger corpus-format datasets, which is corpus-generation
work, which by this pass's own governing constraint must not land in the
same change as anything resolver-adjacent, and would additionally re-trigger
`leakage_audit.py`/`triviality_check.py` gating at an untested scale. Both
of those are real projects, not a flag flip.

**Rejected: skip `scale/` entirely since it only covers the superseded
engine.** The frozen cascade is still the corpus's second baseline in
`corpus/THREE_SYSTEMS.md`, and its throughput was never measured at any
scale beyond the ~1.4s primary-set runtime — "does not scale to a real
merchant book" has been asserted (`SETTLEMENT_SPEC.md` §1.5, this document's
§15) since early in the project and never actually measured. Running the
existing scaffolding closes that specific, cheap gap even though it does not
touch the newer resolver.

**Consequence accepted.** The results document states plainly that resolver
throughput at scale is unmeasured, and names the reason above rather than
omitting it.

---

## 54. The bank-side class is scored by a scorer-local check, and `corpus/oracle.py` is left uncorrected in public view — 2026-08-31

**Decision.** `corpus/score_bankside.py` carries its own `bankside_verdict`
function for the `d12_bank_side_mispost` class. `corpus/oracle.py` is imported
and run unmodified, its gates are reported as the gates, and its *measured,
ungated* `attestation_discrepancy` block is printed **exactly as the oracle
produced it** — including the number it gets wrong — with the re-attribution
shown in adjacent columns rather than applied to it. `BANKSIDE_RESULTS.md`
states in the body that the `verdict` column is a scorer-local check and not
an oracle gate.

**What the oracle cannot represent, measured rather than assumed.** The gates
*do* cover the primary soundness question: G1 fires on a `Verified` whose
composition is not the key's composition, and it is class-agnostic — it reads
`truth["batches"]`, so a bank-side corruption needs nothing added. G7 also
behaves correctly here without knowing about the class: the corrupted line is
in `determined_instances` (the register was computed from the *true* payout),
but `ResolverOutput.abstention_failures` counts only `Unresolved` and
`Ambiguous` as abstention, so an `AttestationDiscrepancy` on that line is not
scored as a missed answer. Neither of those needed checking against the class.

What breaks is one ungated measurement: `_measure` derives
`attestation_discrepancy["planted"]` from
`truth["attestation"]["wrong_attestations"]`, which by construction records
PSP-side wrong attestations only. A `table: "bank"` planted class cannot
appear there. So a **correct** bank-side detection falls through to
`genuinely_false` — the oracle reports 1 genuinely-false finding per dataset
for a finding that is true and planted.

**Rejected: fix `corpus/oracle.py` to count bank-side planted classes.** This
is the obvious change and it is the wrong one to make here. `planted` feeds
the four-way split cited in `ORACLE_RESULTS.md` and `THREE_SYSTEMS.md`;
widening it changes a published false-alarm number across 30 datasets, and it
widens what the oracle *means* by a planted discrepancy, which is contract
vocabulary. §31, §46 and §51 all say the same thing: a change to the oracle or
the contract provoked by corpus work is a separate dated decision, never
folded into the change that provoked it. Doing it here would also mean the
resolver's first bank-side score and the oracle change that scores it landed
together, which is precisely the ordering this project spends its evidence
budget avoiding.

**Rejected: silently correct the number in `BANKSIDE_RESULTS.md`.** Printing
`genuinely_false: 0` because the scorer knows better, without printing what
the oracle actually said, would make the report disagree with the tool it
claims to be reporting. The two columns sit side by side instead; a reader can
see the oracle was not edited.

**Rejected: leave the class unscored beyond the gates.** The gates pass on a
resolver that abstains on every corrupted line, and abstention is exactly the
weaker behaviour this class exists to distinguish from the sound one. Without
`bankside_verdict` the report could not tell "named the disagreement" apart
from "could not explain it", which is the whole question §51 asked.

**Consequence accepted.** `corpus/BANKSIDE_RESULTS.md` reports a check that no
gate enforces, and says so in those words. The follow-up — teaching the oracle
about bank-side planted classes — is now an owed, named change rather than an
undocumented divergence.

---

## 55. A real GST/ITC population axis is added, scored against the frozen filters only, and no resolver work rides along — 2026-08-31

**Decision.** The corpus's GST/ITC leg gains three new `AxisPoint` fields —
`gst_absent_fraction`, `gst_no_irn_fraction`, `gst_37a_fraction` — plus
`gst_vendor_noise_multiplier`, all defaulting to values that reproduce
today's exact fixed-3-index plant (`gst_rows[0]` gets Rule 37A,
`gst_rows[1]` is dropped for Sec 16(2)(aa), a third gets Rule 48(5)) when
unset. A new module, `corpus/generator/gst_population.py`, sibling to
`bank_side_errors.py`, implements the real fractional planting; it replaces
`build.py`'s inline `if len(gateway_invoices) >= 3:` block and never touches
`engine/generator.py` (frozen, and already a separate implementation for the
primary dataset). Two new datasets ship in a new family,
`corpus/datasets_gst/`: `A20_B100_Cmax_gst` (`weeks=52` → ~12 gateway
months instead of ~3, `gst_absent_fraction=1/12`, `gst_no_irn_fraction=1/6`,
`gst_37a_fraction=1/6`, seed `20261001`) and `A20_B100_Cmax_gst_noisy`
(same, plus `gst_vendor_noise_multiplier=12`, seed `20261002`). Both carry
`wrong_attestations=0`, mirroring `BANKSIDE_POINTS`' own isolation
discipline. A new scorer, `corpus/score_gst.py`, mirrors
`corpus/score_bankside.py`'s shape: it runs the existing, unmodified
`matching/stage4_exceptions.py` filters and `resolver/` **read-only**
against the new population and reports `corpus/GST_RESULTS.md`.

**A structural fact this design depends on, verified by reading
`matching/stage4_exceptions.py`'s `_tax_exceptions()`, not assumed.** It
inspects only the gateway's own monthly 2B lines
(`dataset.gstr2b` filtered to `line.gstin == findings.supplier_gstin`); the
third-party vendor-noise rows built alongside them are invisible to the
three statutory filters and only matter as noise `identify_supplier()` must
not be fooled by. Gateway-line variation and vendor-noise variation are
therefore two different knobs, and only the former exercises the filters —
this is why the two new fields for grounds (`gst_absent_fraction` etc.) are
separate from `gst_vendor_noise_multiplier`, and why the second dataset
exists at all: to isolate the noise question from the population question
rather than let a finding in one hide inside the other.

**Why.** `corpus/CORPUS_SPEC.md`'s own limitations table names this
directly, as D9: *"the GST leg has no reconciliation work; 20-row file; all
3 ITC findings are single-column filters at precision 1.000;
`itc_availability == 'No'` supplies the conclusion as an input column."* And
further: *"[the corpus] still has no volume of ITC decisions, no
partially-filed-supplier population, and no IRN timing distribution. Any
GST claim in a headline remains substantially unearned."* This entry closes
those three named absences — volume, a real partial-filing population, a
real IRN-presence population — with the smallest change that does not mint
a lateness case the generator's own commentary already calls mechanically
impossible.

**Rejected: model "IRN generated more than 30 days late."** Both
`engine/generator.py`'s and this corpus's own generator commentary already
establish that the IRP refuses late registration outright, so such a row
never reaches 2B at all — it is indistinguishable from the already-covered
absent-from-2B ground, not a fourth, separate one. Modelling it would add a
field that tests nothing new.

**Rejected: fold `datasets_gst` into `corpus/three_systems.py`'s
`FAMILIES`.** Identical reasoning to §51: that pipeline's dataset counts are
narrative prose in three already-cited, already-audited generated documents.
A two-dataset family whose purpose is exposing a gap gets its own small
report, `corpus/GST_RESULTS.md`, instead.

**Rejected: patch `matching/stage4_exceptions.py` or `identify_supplier()`
in this same change if the new population shows they do not generalize.**
That is `matching/` source — resolver-adjacent work — and this repo's
governing rule is that corpus/dataset work and resolver/matching code
changes never land in the same change. A finding here is written up in
`corpus/GST_RESULTS.md`, not patched.

**Rejected: patch `corpus/oracle.py` in this same change, even if
`score_gst.py` finds it has no tax-leg logic at all.** Per §54's precedent,
an oracle change is its own decision. `score_gst.py` carries a scorer-local
check instead, and states plainly whether the oracle's silence on the tax
leg is total (no gate, no ungated measurement) or partial — checked, not
assumed, since a grep of `oracle.py` for "gst"/"itc"/"2b" returns zero
matches today, which is a different and more basic finding than §54's
miscalibrated-measurement one.

**Rejected: design or build any GST-aware `resolver/` reasoning in this
pass.** `resolver_contract/types.py` already declares
`SourceSystem.TAX_AUTHORITY` and `EvidenceKind.GST_DOCUMENT`, and nothing in
`resolver/*.py` consumes them — `resolver/loaders.py::load()` does not even
open `gstr2b.csv`. Implementing that consumption is a distinct, resolver-side
workstream, out of scope here by the same governing rule as the previous
rejection, and confirmed out of scope by the project owner directly rather
than assumed.

**Scope, stated so it is not overread.** This entry authorizes corpus-side
work only: `corpus/generator/build.py`, the new
`corpus/generator/gst_population.py`, `corpus/score_gst.py`, and adding
`"datasets_gst"` to the hardcoded `FAMILIES` tuples in
`corpus/leakage_audit.py` and `corpus/triviality_check.py` (both scripts
already read `ground_truth.json["planted_classes"]` and scan dataset
directories generically otherwise — the `FAMILIES` tuple is the one place
that needs a name added, per §51's own finding about the same tuple). It
does not authorize any edit to `resolver/`, `matching/`,
`resolver_contract/`, or a same-change `corpus/oracle.py` fix. A dataset
where every new fraction rounds to zero available lines ships without that
ground planted, exactly as `plant_mispost`/`plant_false_composition` ship
without their class when they cannot construct one honestly — no row is
ever minted to force arithmetic to work.

**Consequence accepted.** Whichever of the two outcomes `score_gst.py`
measures — the existing filters generalizing to a real population, or not —
neither licenses a claim that GST/ITC reasoning exists in `resolver/`. That
remains a distinct, unattempted workstream, and `corpus/GST_RESULTS.md`
states this in one explicit sentence rather than leaving it to omission.

---

## 56. The oracle's bank-side attestation accounting is fixed, in its own frame — 2026-08-31

**Decision.** `corpus/oracle.py::_measure`'s `attestation_discrepancy` block
gains a second, explicitly separate computation in bank-line-index space,
alongside the existing settlement_id-keyed one — never merged into it.
`planted` becomes `len(wrong_attested) + len(bank_side_planted_indices)`,
where `bank_side_planted_indices` is read generically from
`truth.get("planted_classes", {})` filtered to `spec.get("table") ==
"bank"`, exactly mirroring `corpus/leakage_audit.py::classes_from_ground_truth`'s
already-generic pattern — no class name is hardcoded, so a future bank-side
class needs no further oracle edit. The `detected`/`true_positive`/`missed`
loops each gain a second, clearly-commented branch checking
`outcome.bank_index in bank_side_planted_indices`, kept visibly distinct
from the `expected["settlement_id"] in wrong_attested` branch rather than
folded into one condition.

**Why.** `DECISIONS.md` §54 diagnosed the bug and deliberately deferred the
fix: *"the oracle was not edited to fix this... The follow-up — teaching the
oracle about bank-side planted classes — is now an owed, named change rather
than an undocumented divergence."* This entry is that owed change. The bug
itself is a reference-frame defect (§44's named class): `wrong_attested` is
a set of settlement ids; `corpus/datasets_bankside/*/ground_truth.json`'s
`planted_classes["d12_bank_side_mispost"]["members"]` is a list of bank-line
indices. `_measure` compared everything as if it were in the first frame,
so a correct bank-side `AttestationDiscrepancy` detection had no matching
settlement id to be found by and fell through to `genuinely_false`.

**Rejected: force the bank-line index through `by_line[...]["settlement_id"]`
into the existing `wrong_attested` set.** This was considered and rejected
as the wrong fix, not merely a less convenient one: it would make the two
frames look unified in the code while remaining conceptually distinct
(a bank line's index and the settlement it happens to correspond to are not
interchangeable keys — `by_line` is itself a lookup FROM one frame TO
information keyed in the other, and using it to erase the distinction is
exactly the move §44 names as the recurring mistake). The two branches stay
separate on purpose, so a reader auditing this code later sees the frame
distinction rather than having to re-derive it.

**Rejected: widen `wrong_attested` itself to include bank-side entries.**
Same objection — `wrong_attested`'s name and every other use of it in this
module (G-gate-adjacent checks, missed-detection reporting) assumes
settlement-id membership. Widening its meaning silently would make every
existing caller subtly wrong in a way not visible at any single call site.

**Consequence, checked not assumed.** This changes
`corpus/BANKSIDE_RESULTS.md`'s published oracle columns:
`genuinely_false: 1 → 0` on both `datasets_bankside/*` datasets (the
"after re-attribution" column that file already prints independently
already showed 0, confirming this fix produces the number the scorer-local
re-attribution logic in `corpus/score_bankside.py` computed by hand). That
file must be regenerated via `corpus/score_bankside.py`, and its "Where the
oracle cannot represent this class" paragraph amended, dated, to say the
oracle was fixed here — while `bankside_verdict`'s per-line
SOUND/UNSOUND/DECLINED/NO_OUTCOME taxonomy is kept, not deleted: this fix
only corrects the *aggregate* `genuinely_false` counter, and the oracle
still has no gate or measurement that fires per-line the way
`bankside_verdict` does, so that scorer-local check still answers a
question the oracle cannot.

**Scope.** `corpus/oracle.py` only. No gate (G1-G9) changes — all nine are
already confirmed class-agnostic (§51, §54). `corpus/three_systems.py`'s
30-dataset aggregate is unaffected: `datasets_bankside/` is not in its
`FAMILIES` tuple and this fix does not add it there.

## 57. §56's bank-side predicate is narrowed from `table` to a declared per-line contradiction — 2026-08-31

**Decision.** `corpus/oracle.py::_bank_side_planted_indices` implements §56 with
one deviation, recorded here rather than silently: a planted class qualifies as
a bank-side attestation discrepancy when it is `planted`, `table: "bank"`, **and**
its `detail` entries each carry both `bank_line_index` and `settlement_id` —
i.e. the class itself declares, per member line, a contradiction against a named
settlement. §56 specified `spec.get("table") == "bank"` alone. No class name is
hardcoded either way, so §56's stated intent (a future bank-side class needs no
further oracle edit) is preserved.

**Why, measured not assumed.** `table: "bank"` alone is not a predicate for
"attestation discrepancy". Two other classes are also `table: "bank"`, in **all
34** corpus datasets: `d01_settlement_reversal` (1 member) and
`d02_foreign_bank_lines` (7 members). Neither is a discrepancy — a reversal is a
correctly recorded reversal, which `_measure` already accounts for separately as
`true_finding_of_another_kind` via `reversed_settlements`, and a foreign bank
line is a third party's money that the resolver is right to leave alone. Under
the literal §56 predicate the two bank-side datasets would report
`planted = 9` with 7 entries in the new `planted_but_missed_bank_side`
collection: a published claim that the resolver missed seven planted
discrepancies on lines where there is nothing to detect. It would also have
moved the reversal detection out of `true_finding_of_another_kind` into
`correctly_identified`, erasing the distinction the FOUR-WAY split exists to
make. §56 predicted its own consequence as `genuinely_false: 1 → 0` and nothing
else; the literal predicate does not produce that, and the narrowed one does.

**Blast radius, checked.** `_bank_side_planted_indices` returns a non-empty set
on exactly the two `corpus/datasets_bankside/` datasets ({19} and {14}, the two
planted misposts) and the empty set on all 32 others, verified by running it
over every `corpus/datasets*/*/ground_truth.json`. `corpus/three_systems.py`,
`corpus/scorecard.py` and `corpus/claims_ledger.py` all aggregate
`attestation_discrepancy.planted`, so the literal predicate would have made
their published 30-dataset numbers stale by +272 planted; the narrowed one
leaves them bit-for-bit unchanged, which is what §56's own scope paragraph
requires.

**Rejected: implement §56 literally and absorb the wrong numbers.** The whole
point of §56 is that the oracle should count planted discrepancies correctly.
Trading a false `genuinely_false` for a false `planted_but_missed` is not a fix.

**Rejected: discriminate on `members` being strings rather than ints.** It
happens to work today (`d12`'s members are `["19"]`, `d01`/`d02`'s are ints) and
is pure coincidence of serialisation. It would break the first time a generator
normalised its types, and it encodes nothing about what the class means.

**Rejected: keep `table == "bank"` and subtract the two known class names.**
That is the hardcoded-class-name coupling §56 explicitly refused, restored in
negative form.

**Scope.** `corpus/oracle.py` and the report text in `corpus/score_bankside.py`.
No gate changed; G1–G9 were re-read and confirmed class-agnostic (none reads
`planted_classes`). §56 is not edited — DECISIONS.md is append-only.

---

## 58. `resolver/enumerate_closures.py` still budgets in WALL-CLOCK seconds — §49's defect, fourth instance, and it is DOCUMENTED here rather than fixed — 2026-08-31

**The finding.** `resolver/resolve.py` is not reproducible run-to-run on a
dataset large enough that any bank line's closure enumeration hits its time
budget. `resolver/enumerate_closures.py:closing_subsets` sets

```
solver.parameters.num_workers = 1          # determinism across runs
solver.parameters.max_time_in_seconds = time_budget
```

with `time_budget` defaulting to `10.0` (`DEFAULT_TIME_BUDGET`, and
`resolve(..., time_budget: float = 10.0)`). `num_workers = 1` fixes the search
*order*; it does not fix where a **wall-clock** budget cuts that order off.
Two runs of the same search on the same machine stop at different points
depending on what else the machine was doing, so a truncated enumeration
returns a different subset set, and `resolve()` can return a different
`composition` for the same bank line.

**How it was found — not by review.** `resolver/tests/test_gst_risk.py::
test_removing_the_gst_feed_changes_nothing_but_the_annotation` (§ the GST
annotation capability) resolves `corpus/datasets_gst/A20_B100_Cmax_gst` twice
and asserts the two `line_outcomes` tuples are identical. It was reported
passing when written; it then failed on two independent subsequent runs of
`pytest resolver/tests`, at bank index **56** on one run and **58** on
another. Filesystem and process-startup variance were then eliminated by
calling `resolve()` three times on the **identical in-memory `Dataset`
object** inside one Python process:

```
run 0: 30.45s, 59 outcomes
run 1: 30.42s, 59 outcomes
run 2: 30.41s, 59 outcomes
run0 == run1: False
run1 == run2: True
first diff at index 56: bank_index=56, both Verified, different composition
```

Two `Verified` outcomes, same line, same input object, different composition.
That is the whole defect in three lines of output.

**Instrumented, so the mechanism is measured and not inferred.** Wrapping
`closing_subsets` over one `resolve()` of that dataset:

| `time_budget` | wall | enumerator statuses |
|---|---|---|
| 10.0 | 31s | 49 `optimal`, 3 `infeasible`, **2 `time_budget_exceeded`** |
| 60.0 | 86s | 49 `optimal`, 3 `infeasible`, 1 `cap_reached`, **1 `time_budget_exceeded`** |

Exactly the two lines that do not complete are the two the test disagreed on.
Raising the budget six-fold does not close the hole: one pool (33 rows) still
exhausts 60 seconds without proving completeness, and a second (34 rows) merely
converts into `cap_reached` at 200 subsets.

**Root cause, and it is a known one in this repository.** This is §39's class
and §49's exact remedy, one component over. §49 replaced
`max_time_in_seconds` with `max_deterministic_time` at both CP-SAT call sites
in `matching/stage3_solver.py` for precisely this reason — OR-Tools'
deterministic-time budget is its own published mechanism for run-to-run
reproducibility irrespective of wall-clock conditions — and §50 then fixed the
adjacent `truncated` predicate in the same function. `resolver/
enumerate_closures.py` was written before that lesson existed and never
received the equivalent change. §39's own fix in this file corrected
`complete` (the soundness claim) and deliberately left the `timed_out` label
line alone as evidence (see its FRAME comment, §44 instance F3); nobody in
that pass looked one line further up at the `parameters` block. §44.4's claim
— that this class is not eliminable by care, only by repeated passes — now has
a fourth instance, and this one is in the resolver written to prevent it.

**Decision: fixing `enumerate_closures.py` is OUT OF SCOPE here.** This entry
documents the finding; it changes no solver parameter. The fix is a swap of
`max_time_in_seconds` for `max_deterministic_time` (and a decision about what
numeric budget to carry, which §49 records as *not* having a published
conversion), and it will move published resolver numbers on every dataset with
a truncating pool — which means it needs its own dated decision, its own
committed-before-the-fix prediction, and its own before/after pair, exactly as
§49 and §50 each got. Doing it inside a task whose scope is a GST test would
produce a parameter change with no prediction, no measured blast radius, and no
recomputed downstream figures. §44's standing treatment of "found while doing
something else" is to record it and let it have its own cycle; §50 is the
precedent for the follow-on actually happening.

**What this means for existing claims, named rather than hunted.** Any
byte-identical-across-runs claim about `resolver/` output on a dataset large
enough to truncate is, until the fix lands, a claim about one draw. The
mechanism is stated here; deciding which specific published figures need
re-verification belongs to the pass that makes the fix, because that pass has
to recompute them anyway. Two things bound the exposure and are worth stating:
`complete` is still sound (§39 — it is `status == OPTIMAL` and nothing weaker),
so a truncated enumeration cannot be promoted to `Reconstructed`; and the
frozen cascade's own baseline is unaffected, since `matching/stage3_solver.py`
was fixed in §49.

**The consequence taken now, and only this one.** The GST test above is not
about closure enumeration and must not be hostage to a defect that has nothing
to do with GST. It is rebuilt on a small synthetic dataset written in the test
itself — seven rows, two bank lines, four closure enumerations, all four
`optimal`, whole run 0.03s — so the mechanical proof it exists to make runs
entirely outside the truncating regime rather than working around the trigger
with a larger number. A companion test resolves that fixture twice and asserts
equality, so if it is ever grown into the slow regime the suite says so
directly instead of flaking.

**Rejected: raise `time_budget` to 60.0 on the two `resolve()` calls in the
test.** Measured above: it does not work. One pool still times out at 60s, and
the test would have gone from 60 seconds to 175 while remaining flaky — the
worst of both.

**Rejected: use the other GST dataset, or a smaller corpus dataset.** There are
exactly two GST datasets and they are the same size (`A20_B100_Cmax_gst` and
`A20_B100_Cmax_gst_noisy`, both `weeks=52` for population volume). No smaller
one exists, and the test needs a GST feed.

**Rejected: keep the SPINE and skip the two bank lines that truncate.** Choosing
which lines to compare by whether they agree is not a proof of anything, and the
selection would have to be re-derived every time the machine got faster.

**Rejected: fix `enumerate_closures.py` here and note it in passing.** See the
decision paragraph. A silent parameter change to the resolver's solver, made
while editing a test, is the shape of change this repository's whole
DECISIONS/prediction discipline exists to prevent.

**Scope.** `DECISIONS.md` (this entry) and `resolver/tests/test_gst_risk.py`.
No file under `resolver/` other than that test, and no file under `matching/`,
`corpus/` or `resolver_contract/`, is touched.

---

## 59. GST evidence reaches `resolver/`, and it may only ever annotate an `OpenBreak` — 2026-08-31

**Decision.** `resolver/loaders.py::Dataset` gains a fifth optional file,
`gstr2b`, following the exact pattern already established for
`settlement_report`/`erp_order_ids`/`disputes`: a new `Gstr2bLine` frozen
dataclass, field-identical to `matching/loaders.py`'s own (defined locally,
not imported — the two packages stay independent, the same reason `resolver/`
shares no other code with `matching/` or `engine/`), `.exists()`-checked,
empty by default. `resolver/breaks.py` gains `_itc_risk_months(dataset)`,
reimplementing (not importing) the shape of
`matching/stage4_exceptions.py`'s gateway-GSTIN identification and its three
statutory checks, month-keyed rather than row-keyed (there is no per-payment
`invoice_no` on a recon row — ITC risk is a property of a settled month, not
a single row). `OpenBreak` gains two additive fields,
`itc_risk: frozenset[str]` and `itc_risk_grounds: tuple[str, ...]`, wired
into `dispositions()` — the sole `OpenBreak`-construction point, called at
the very end of `resolve()`, after every `Verified`/`Ambiguous`/
`Determinate`/collision-resolution decision is already final.

**Why.** `resolver_contract/types.py` has declared
`SourceSystem.TAX_AUTHORITY`/`EvidenceKind.GST_DOCUMENT` since the contract
was first written, and nothing has ever consumed them — `resolver/loaders.py`
did not even open `gstr2b.csv` (§55's own read-only probe confirmed this).
`EVIDENCE_SEMANTICS[GST_DOCUMENT] = Attests.ROW_EXISTENCE`: a 2B line can say
an invoice exists; it can say nothing about which rows composed a bank
credit. That restriction is the whole of this decision's shape — GST
evidence is confined to `OpenBreak`, the one outcome that already asserts
nothing and is never consumed by anything downstream.

**Rejected: using GST absence to eliminate or narrow candidate compositions
("ambiguity-breaking").** Considered and explicitly declined for this pass.
It is structurally the same move as the resolver's own `D1` defect
(`investigation/DEFECT_REPORT.md`) and the "residual reconstruction" already
rejected in §38: using an evidence source to filter or rank candidates before
`CandidateSet`'s enumeration is complete, which `CandidateSet.__post_init__`
raises `ContractViolation` to prevent. A `ROW_EXISTENCE`-only evidence kind
informing which rows are even eligible for a subset-sum pool would need its
own contract-level design and its own dated amendment (the way G8 got one in
§31) — not something to slip in as a side effect of adding a loader.

**Rejected: import `matching/loaders.py::Gstr2bLine` and
`matching/stage4_exceptions.py`'s logic rather than reimplement.**
`resolver/tests/test_isolation.py` forbids the import outright, and the
reasoning is the same one that already keeps `resolver/` from sharing code
with the frozen generator: a bug in one package must not become invisible to
the other's test suite by construction. The accepted cost is duplication risk
— two independent implementations of one statutory rule can drift — mitigated
by a mandatory cross-check test asserting the two agree on every
`corpus/datasets_gst/*` dataset. They agree today, with a genuine
implementation difference recorded rather than hidden: `resolver/breaks.py`
attributes a row's month via `first_reconcilable` (the row has already failed
to be placed by the time `dispositions()` sees it, so `settled_at` is an
unconfirmed PSP claim at best), where the dataset-level monthly fee accrual
still uses `settled_at`, matching the reference exactly on that half — which
is why the cross-check passes.

**Rejected: reuse `BreakReason.MISSING_SOURCE` instead of new `OpenBreak`
fields.** A break's `reason` answers why it is open; ITC exposure is an
independently-true-or-false fact about the same rows, not a root cause —
conflating the two loses information whenever both apply, and
`MISSING_SOURCE`'s routing (`data ops`, "the missing artefact arrives") is
the wrong owner for a tax-ops finding in any case.

**Verified, not assumed: this cannot touch a composition.** `dataset.gstr2b`
does not appear anywhere in `resolver/resolve.py` upstream of the
`dispositions(...)` call (checked by grep, not by reading intent into the
code) — the safety property is therefore checkable by one search, not an
audit of every construction site. `resolver/tests/test_gst_risk.py` makes
this mechanical: every non-`OpenBreak` outcome is asserted byte-identical
with and without `gstr2b.csv` present, and no `Verified`/`Ambiguous`/
`Reconstructed`/`AttestationDiscrepancy`/`Determinate` warrant is ever found
to carry `GST_DOCUMENT` evidence, across every GST dataset.

**A defect found while building this, documented separately, not fixed
here.** The mechanical no-op test above, run against the large `weeks=52`
GST spine dataset, surfaced a genuine, pre-existing, unrelated resolver
nondeterminism — `resolver/enumerate_closures.py`'s wall-clock time budget,
the same defect class as §39/§49/§50, its fourth instance, this time in code
this decision did not write and does not fix. See §58. The test itself was
rebuilt against a small, fully-`optimal` synthetic fixture instead, so the
GST proof no longer depends on a bug orthogonal to what it is proving.

**Scope.** `resolver/loaders.py`, `resolver/breaks.py`,
`resolver_contract/types.py` (additive `OpenBreak` fields only),
`resolver/tests/test_gst_risk.py`. `resolver/resolve.py`'s control flow is
read, not edited. No file under `matching/`, `engine/`, or `corpus/` is
touched.

---

## 60. The resolver's ITC-risk flag gets a number before it gets a threshold — MEASURED, NOT GATED, and it scores 0.0 — 2026-08-31

**Decision.** `corpus/oracle.py::_measure` gains one block, guarded by
`"gst_truth" in truth` so it is a silent no-op on all 30 non-GST datasets:
`measured["itc_risk_flag"]`, computed by a new `_itc_risk_flag(output,
truth)`. It scores §59's two additive `OpenBreak` fields — `itc_risk` and
`itc_risk_grounds` — as `(row_id, ground)` pairs against the corpus key.
`corpus/score_gst.py` surfaces it as a new section in `corpus/
GST_RESULTS.md`. **No G-numbered gate is added, no existing gate G1-G9 is
touched, and no other measured statistic is touched.**

**Why measured and not gated.** §59 is the first contact between `resolver/`
and `gstr2b.csv` in any form, and `resolver/breaks.py` deliberately
*reimplements* the gateway-GSTIN identification and the three statutory
checks rather than importing `matching/stage4_exceptions.py` — §59 records
that duplication-drift risk as accepted, with a cross-check test as the
mitigation. Gating an untested reimplementation's **first** measured numbers
is precisely the mistake **G5** was withdrawn for: a threshold asserted on a
proposition nobody had yet measured, which the corpus's own data then
falsified. A number has to exist before a threshold on it can mean anything.
The `reconstructed_accuracy` block is the template followed here, down to the
`note` string: a weaker claim, so errors are measured rather than gated — but
they are still errors and are still reported.

**The result, stated first because it is bad.** Over
`corpus/datasets_gst/A20_B100_Cmax_gst`: 22 rows sit in some `OpenBreak`, the
resolver flags 4 of them, and **all 4 are false positives. Precision 0.0, TP
0, FP 4.** Over `A20_B100_Cmax_gst_noisy` the flag fires on nothing at all: 0
flagged, 0 true pairs, so precision and recall are both **undefined and
reported as `None`, never as 1.0** — an untested flag and a correct flag
produce the same silence and this repository will not conflate them. Recall
is undefined at *both* seeds, because no settled row from an at-risk month
reached an `OpenBreak`; nothing measured here says whether the flag would
find a genuine exposure.

**The cause is measured, not inferred, and it is one line of the table.**
`flagged_rows_that_never_settled` equals `flagged_rows` — 4 of 4. All four
rows (two `on_hold_dispute`, two `not_yet_eligible_at_horizon`) have
`settled_in = None` in the key. The gateway never invoiced a fee against
them, so they carry no input tax that could be at risk. §59 attributes a row
to a month by `first_reconcilable`, which put them in `2027-12` — a month
that genuinely carries a `gstr2b_no_irn` finding, but carries it on behalf of
that month's *settled* population.

**Two frames, deliberately not reconciled.** The resolver's frame is
`first_reconcilable`, and §59 argues for it: every row reaching
`dispositions()` is one nothing placed, so `settled_at` is an unconfirmed PSP
claim on it. The oracle's frame is read from the key alone — `settled_in` →
`batches[].formed_at` → `"%Y-%m"` — and never calls, imports, or reproduces
`first_reconcilable`. **Rejected: deriving the truth side from
`first_reconcilable` too**, which is what "make the numbers comparable" would
have meant in practice. It would make the row→month attribution shared
between the thing measured and the thing measuring it, and the statistic
would then be structurally incapable of seeing an attribution error — §44's
named defect class, and the same move §56 already rejected once on the
bank-side accounting. The disagreement between the two frames **is** the
measurement.

**Scope of the universe, stated rather than implied.** Precision/recall range
over rows appearing in some `OpenBreak`, because §59 confines this annotation
to `OpenBreak` outright. A row the resolver correctly settled is neither
flagged nor flaggable, and counting it as a false negative would measure the
contract's own restriction rather than the flag. Pairs are the cross product
of a break's flagged rows with its `itc_risk_grounds`, which is a per-break
union; `breaks_straddling_months` reports how often that cross product could
be lossy (**0 at both seeds**) rather than asking the reader to assume it
isn't.

**Rejected: fixing the resolver in this pass.** The obvious change — flag
only rows the resolver has some reason to think settled — is a change to
`resolver/breaks.py` made in direct response to an oracle number produced by
the same pass, with no prediction committed beforehand. That is the shape §58
just refused for `enumerate_closures.py` and the shape §49/§50 each got their
own dated cycle for. This entry publishes the 0.0 and changes no resolver
line.

**Rejected: reporting precision alone, or suppressing the undefined cells.**
A precision-only table would hide that recall is undefined at both seeds,
which is the more important limitation: the *whole* at-risk-and-open
subpopulation is empty here, so this is a one-sided measurement and the
report says so in those words.

**Two now-false sentences in `corpus/score_gst.py`'s own generated prose were
corrected rather than left standing.** That file claimed "a grep of
`corpus/oracle.py` for gst/itc/2b returns zero matches" (this entry makes it
23 lines — now counted live by `oracle_gst_grep()`, not typed), and claimed
`resolver/loaders.py::load()` "does not open `gstr2b.csv` at all", which §59
made false. The removal probe is kept and its *question* changed: it no
longer asks whether the file is read, it asks whether reading it moves any
line outcome — §59's actual safety property. It does not, at both datasets.

**Scope.** `corpus/oracle.py`, `corpus/score_gst.py`, the regenerated
`corpus/GST_RESULTS.md` / `corpus/gst_results.json`, and this entry. No file
under `resolver/`, `resolver_contract/`, `matching/`, `engine/` or
`corpus/generator/` is touched, and `corpus/three_systems.py`,
`corpus/scorecard.py` and `corpus/claims_ledger.py` are not touched either.

---

## 61. The ITC-risk flag is gated on the ROW's own settlement, not on its month's — the fix §60 measured and deliberately deferred — 2026-08-31

**Decision.** `resolver/breaks.py` names one predicate, `_accrues_input_tax(row)`
— `type == "payment"` and `settled_at` and `fee` and `tax` — and uses it in the
**two** places that must not disagree: `_fee_accrual`, which decides which
months are at risk, and the per-row annotation loop in `dispositions()`, which
decides which rows may be told about it. The row-level flag becomes a
conjunction:

```python
# before
flagged = sorted(row_id for row_id in row_ids
                 if _month(rows_by_id[row_id]) in at_risk)
# after
flagged = sorted(row_id for row_id in row_ids
                 if _accrues_input_tax(rows_by_id[row_id])
                 and _month(rows_by_id[row_id]) in at_risk)
```

`_itc_risk_months` is **not changed** — it was never wrong. It answers a
month-level question correctly; §59 wired its answer to rows without asking
whether the row belonged to the population the answer was about.

**The bug, stated as the thing it actually was.** A month is at risk *on behalf
of the settlements that accrued fees in it*. §59 attributed an open row to a
month via `first_reconcilable` and flagged it if that month appeared in
`_itc_risk_months`, with no test that the row itself had generated any input
tax to lose. So the flag propagated a population-level property to individuals
who were not in the population. §60 measured the consequence and published it:
on `corpus/datasets_gst/A20_B100_Cmax_gst`, 4 rows flagged, **4 false
positives, precision 0.0**, and its `flagged_rows_that_never_settled` line was
already 4-of-4.

**One part of §60's diagnosis is corrected here rather than repeated.** §60's
prose, and §59's own comment on the grouping key, suggest the false positives
arose because the rows *shared an `OpenBreak` with rows that did settle*. They
did not: all four breaks are **single-row** (verified by inspection of the
resolved output, not assumed). The sharing is with the calendar month
`2027-12`, which carries a genuine `gstr2b_no_irn` ground on behalf of that
month's settled population. The break-grouping key is a red herring; the fix is
the same either way, and the new test asserts the stronger property — two rows
in *one* break, only the settled one flagged — so it holds under both readings.

**`fee` alone would not have caught it, and this was checked rather than
assumed.** All four false positives carry a non-zero `fee` and `tax` on the
ledger row; they are *prospective* charges on payments that never paid out
(`unsettled_reason`: two `on_hold_dispute`, two `not_yet_eligible_at_horizon`).
`settled_at` is the load-bearing clause. Across all 22 rows in some `OpenBreak`
on the spine, the resolver-visible `settled_at` agrees with the key's
`settled_in` on every row — so the gate is discoverable from the feed alone and
needs nothing the resolver may not see.

**What the fix does to the number, stated before anyone re-runs it.** The spine
now flags **nothing**: of its 22 open rows, the 4 that accrued input tax settled
in `2027-01`, which carries no ground, and the 18 in at-risk months accrued
none. The intersection is empty. So precision goes from `0.0` to *undefined*,
not to `1.0` — this removes 4 wrong answers and adds no right ones, and §60's
finding that recall is undefined at both seeds is unchanged and remains the more
serious limitation. A subsequent step re-runs `corpus/score_gst.py`; this entry
does not, and neither `corpus/oracle.py` nor `corpus/score_gst.py` is touched.

**This is NOT the pattern this repository forbids, and the distinction is
structural, not a plea.** The prohibition is on tuning *in response to held-out
results* — `holdout/SEED.txt`'s protocol, and the reason §58 refused to fix
`enumerate_closures.py` inside the pass that found it. Three things make this
different, each checkable:

* **No held-out GST data exists.** `corpus/datasets_gst/` is the known,
  developed-against set. There is nothing here that could be spent.
* **The measurement already got its own dated cycle.** §60 published the 0.0,
  named the cause, and *explicitly deferred the fix* — "Rejected: fixing the
  resolver in this pass … This entry publishes the 0.0 and changes no resolver
  line." The prediction is committed, in `git log`, before this change. That is
  precisely the measure-then-fix-in-a-separate-dated-entry shape §49/§50 each
  got, and the shape §58 asked for.
* **The fix is not shaped to the score.** It is a predicate the module already
  contained, applied to a second call site. It would be the correct code with no
  corpus at all, and it changes behaviour on a dataset only by *removing*
  claims. Nothing was swept, no threshold was chosen, no seed reselected.

**Rejected: switching the row→month attribution from `first_reconcilable` to
`settled_at`.** Now that a flagged row must have a `settled_at`, §59's stated
reason for `first_reconcilable` ("it is null outright for an unsettled row")
no longer bites — but its other half does: `settled_at` is a PSP claim the
resolver could not corroborate, which is *why* the row reached `dispositions()`.
More decisively, the oracle's frame is `settled_in → batches[].formed_at`, and
adopting it inside the resolver would make the row→month attribution shared
between the thing measured and the thing measuring it — §44's named defect
class, rejected on the same grounds by §56 and again by §60 (which refused the
mirror-image move on the truth side). The two frames stay unreconciled; their
disagreement is still the measurement.

**Rejected: making `_fee_accrual` itself use the predicate as its outer
guard.** It reads as the obvious tidy-up and it would have changed behaviour. A
fee-bearing row with no GST on it currently *opens* its month's bucket while
contributing nothing to either leg, and that asymmetry is load-bearing for
`gstr2b_absent`: the month saw settlement activity, so it is a month a 2B line
can be missing from. The predicate is therefore shared at the contribution
point only, and `_fee_accrual`'s outputs are byte-identical to before — which is
why all five of §59's `_itc_risk_months` unit tests, including
`test_a_fee_with_no_gst_on_it_accrues_no_taxable_value`, pass unmodified.

**One existing test was inverted, and the inversion is recorded rather than
quietly applied.** `test_the_spine_dataset_actually_flags_something` asserted
that the spine flags something. It passed *because of the bug* — the four rows
it was satisfied by are the four false positives. It is replaced by
`test_the_spine_flags_nothing_because_it_has_nothing_to_flag`, which asserts the
emptiness **together with its reason**: that both operands (open rows that
accrue input tax; open rows in an at-risk month) are non-empty and their
intersection is not, so it cannot be satisfied by a flag wired to a constant
`False`. §59's no-op proof does not lose its non-vacuity guard — that lives on
the small fixture inside
`test_removing_the_gst_feed_changes_nothing_but_the_annotation`, which still
flags and still passes untouched. A new test,
`test_a_row_that_never_settled_is_not_flagged_by_its_break_mate`, puts two rows
identical in every field the grouping key reads into one `OpenBreak` in an
at-risk month and requires exactly the settled one back. It was negative-
controlled: with the predicate forced to `True` it returns both rows and fails.

**Verification.** `resolver/tests` run three times, 21 passed each time,
including the §58-sensitive small-fixture tests — this change adds no dependency
on the SPINE dataset for any determinism claim.

**Scope.** `resolver/breaks.py`, `resolver/tests/test_gst_risk.py`, and this
entry. Nothing under `matching/`, `engine/`, `corpus/`, `resolver_contract/`,
and no other file under `resolver/`, is touched. `corpus/GST_RESULTS.md` is
deliberately left stale for a later step to regenerate.

---

## 62. `score_gst.py`'s closing paragraph was hand-typed prose, not a generated claim — found and fixed regenerating after §61

**Decision.** Regenerating `corpus/GST_RESULTS.md` after §61's fix, its
closing "The answer" section still read "precision 0.0, every flagged row
one that never settled" — the pre-§61 numbers, hardcoded as a literal string
in `corpus/score_gst.py` rather than derived from the `results` this same
function already computes (`zero_precision`/`silent`/`perfect`, used
correctly two sections earlier in the same file). Two spots fixed: the
"Recall is undefined..." sentence's closing clause (`"wrong or silent"` was
unconditional; now selects among `"wrong"`/`"wrong or silent"`/`"silent"`
from the live lists) and the final paragraph (now branches on
`zero_precision`/`silent`/neither, describing whichever state the
measurement actually shows, including a phrase crediting §61's fix when
false positives are the thing that went away). Regenerated; the file now
reads correctly against the post-§61 measurement.

**Why.** This repo's own rule, stated in a dozen places and enforced by the
convention that every generated `.md` file is written by a script from a
live run: no number or claim in a generated report may be hand-typed,
because a hand-typed claim is exactly the kind of thing that goes stale the
moment the code it describes changes — which is precisely what happened
here, one step later in the same pass.

**Scope.** `corpus/score_gst.py` only (the two paragraph-generation sites),
plus a regeneration of `corpus/GST_RESULTS.md`/`corpus/gst_results.json`.
No file under `resolver/`, `matching/`, `engine/`, or `resolver_contract/`
is touched.

---

## 63. The resolver+oracle GST code is frozen, by content hash, before any held-out data exists — 2026-08-31 17:23 IST

**Decision.** §55-§62's entire GST/ITC pass — the corpus population axis,
the resolver's `gstr2b` loading and `itc_risk` flagging, the row-attribution
fix, and the oracle's measured (not gated) `itc_risk_flag` statistic — is
declared frozen as of this entry. SHA-256 of every file this pass touched
under `resolver/`, `resolver_contract/`, and the scoring path, taken at
17:23 IST, 2026-08-31:

```
dec87ace1aa7f4c8accb88494842306df8cdd1b601d0e2e95f9f7303a11e9e05  resolver/loaders.py
bfd91818c15bfcaf2f801951bd9c0560f6f0a3ad876d9a4382d73a642e8b996b  resolver/breaks.py
9b72981c4399b0adddcec55a74492526180171e37fe882d77af3405386f6cbb1  resolver/resolve.py
83842068b93d3fc9ad45d8b598a4778e120b32ad1610449ec7476fe0511deeaa  resolver_contract/types.py
edfadde49c694af90bce0082b45fbbb57d4bf8384790c3ff3c68fd693b219d09  corpus/oracle.py
7da59dd119581f0971ded4ff74d2c528e0242bc7c659a3a71f6bd73866bea4b5  corpus/score_gst.py
```

From this point forward, no line in any of these six files may change until
the held-out run (§64 onward) has executed and reported. If any of them
must change for a genuine, unrelated reason before that run happens, this
entry is superseded by a new one recording new hashes and stating why —
never silently.

**Why a hash, not a commit.** This entire pass (§51-§62) sits uncommitted in
the working tree — nothing has been committed in this session, by the
project owner's own instruction to hold everything for review before
committing. `holdout/`'s own protocol cites a frozen *commit* (`81c04e0`)
because that work landed as committed history before the held-out run. That
mechanism isn't available here yet, and simulating it with a premature
commit would be a bigger, unrequested action than this decision warrants.
A SHA-256 per file is the same property stated the only way currently
verifiable: content, not history. `shasum -a 256 -c` against this block at
any later point proves whether these six files are still exactly what the
held-out run was scored against.

**Rejected: commit now solely to get a citable hash.** The project owner
has not asked for a commit at any point in this pass, and creating one only
to produce a hash for this entry would be scope creep for a decision that
doesn't need it — the content hash carries the same evidentiary weight for
the one thing that matters here (did the code change between the freeze and
the run), and is strictly local to this repo, requiring no push or history
rewrite risk.

**What is NOT frozen.** `corpus/generator/build.py`, `corpus/score_gst.py`'s
own report-writing prose beyond what's hashed above is not a target of this
freeze (only the file's exact bytes are, and they're already hashed), and
any file under `corpus/datasets_gst/` — none of that is read by the held-out
run, which only touches its own new dataset directory and the six frozen
files above.

**Consequence.** The held-out results document (§64 onward) must state this
hash block again and re-verify it holds at the moment of the run — a claim
of "frozen before the run" that cannot be checked is not evidence, per this
whole pass's own standard.

## 64. The held-out GST/ITC run executed — freeze held, gates passed clean, no code changed on the result — 2026-08-31

**Decision.** `corpus/SEEDS.txt`'s "## 3. GST/ITC HELD-OUT" addendum and
§63's freeze are executed, once, in full. `corpus/generator/build.py` gains
one new `AxisPoint`, `A20_B100_Cmax_gst_holdout` (`family=
"datasets_gst_holdout"`, `seed=20261013`), identical in population to the
developed-against spine point `A20_B100_Cmax_gst` in everything but seed and
family. `corpus/datasets_gst_holdout/` did not exist before this entry —
confirmed by a failing `ls` immediately before generation, mirroring the
ordering evidence the rest of this pass relies on. Generation produced 314
rows / 51 batches / 59 bank lines on the first and only attempt.

**Freeze verified twice, matching in both directions.** `shasum -a 256` on
`resolver/loaders.py`, `resolver/breaks.py`, `resolver/resolve.py`,
`resolver_contract/types.py`, `corpus/oracle.py`, `corpus/score_gst.py`
immediately before generation, and again immediately after scoring,
reproduced §63's exact six hashes both times:

```
dec87ace1aa7f4c8accb88494842306df8cdd1b601d0e2e95f9f7303a11e9e05  resolver/loaders.py
bfd91818c15bfcaf2f801951bd9c0560f6f0a3ad876d9a4382d73a642e8b996b  resolver/breaks.py
9b72981c4399b0adddcec55a74492526180171e37fe882d77af3405386f6cbb1  resolver/resolve.py
83842068b93d3fc9ad45d8b598a4778e120b32ad1610449ec7476fe0511deeaa  resolver_contract/types.py
edfadde49c694af90bce0082b45fbbb57d4bf8384790c3ff3c68fd693b219d09  corpus/oracle.py
7da59dd119581f0971ded4ff74d2c528e0242bc7c659a3a71f6bd73866bea4b5  corpus/score_gst.py
```

**Gating passed cleanly, no re-seed.** `"datasets_gst_holdout"` was added to
the family tuples already used for `"datasets_gst"`/`"datasets_bankside"` in
`corpus/leakage_audit.py` and `corpus/triviality_check.py` — mechanical,
one line each, no algorithm touched. `corpus/leakage_audit.py --all`:
35/35 datasets pass, including the new one. `corpus/triviality_check.py
--all`: the held-out dataset scores identically to its developed-against
sibling (`51/52 line->batch`, `51/51 composition`, `0.0%` resistance,
`TRIVIAL`) — an expected outcome for this family, since `datasets_gst`'s
triviality was never the axis this population was built to test. Neither
gate needed a generator bug fixed, and the seed was never reselected or
swept — unlike the one precedent (`A20_B100_Cmax_gst_noisy`'s original seed
20261002, re-seeded per §32's practice before any of this pass's data
existed), this seed did not need it.

**`corpus/score_gst.py` needed NO edit.** Its existing positional `dataset`
argument already accepts an arbitrary directory, bypassing the hardcoded
`FAMILY = "datasets_gst"` module constant entirely. It was invoked exactly
once: `python3 corpus/score_gst.py
corpus/datasets_gst_holdout/A20_B100_Cmax_gst_holdout --out
corpus/GST_HOLDOUT_RESULTS.md --json corpus/gst_holdout_results.json`. Its
own bytes are unchanged from §63's hash, confirmed above. A separate,
non-frozen script prepended the freeze/seed citation header to the
resulting `corpus/GST_HOLDOUT_RESULTS.md` — that header is prose and a
freshly-recomputed hash printout, not a scored statistic, so it did not need
to come from inside the frozen scorer.

**The measured result, stated plainly.** On this one held-out dataset: all
three statutory grounds (`gstr2b_absent`, `gstr2b_no_irn`,
`gstr2b_37a_exposure`) score precision/recall 1.0/1.0; `identify_supplier()`
finds the correct gateway GSTIN; the `itc_availability` single-column
shortcut still fails to generalize exactly as documented (misses the
Rule-37A-only invoice and cannot see the absent-from-2B invoice at all,
1 of 2 true-at-risk-and-present invoices flagged); the total ITC-at-risk
rupee figure disagrees by 1 paise, entirely on the `gstr2b_absent` ground,
for the same structural rounding-basis reason §-adjacent text in
`corpus/GST_RESULTS.md` already names (accrued vs. aggregate tax basis for
an invoice that no longer exists in the file); all G1-G9 gates pass; the
`gstr2b.csv`-removal probe shows line outcomes identical with and without
the file, confirming the tax feed still cannot move a composition decision.
**The resolver's `itc_risk` flag — the one number this whole freeze exists
to test out-of-sample — scores precision 1.0 / recall 0.75** (3 of 4
truly-at-risk-and-settled rows flagged, 0 false positives, 1 false
negative), on data neither the flag's attribution fix (§61) nor its
measurement code (§60) was ever run against before. This is a single
measurement on one dataset, not a validated capability, and is reported as
such in `corpus/GST_HOLDOUT_RESULTS.md`.

**No code under `resolver/`, `resolver_contract/`, or `corpus/oracle.py` was
changed in response to what this run found, regardless of the result.**
This is the load-bearing sentence of the entire held-out exercise. The
recall-0.75 result — the first miss this flag has produced against any
dataset — was left exactly as measured. No new fix, no new gate, no
retroactive threshold. `corpus/GST_HOLDOUT_RESULTS.md` is a new file,
reporting this dataset alone; `corpus/GST_RESULTS.md` (the two
developed-against datasets) is untouched.

**Rejected: fixing the recall-0.75 gap now that it's visible.** The
addendum in `corpus/SEEDS.txt` permits fixing a genuine bug in
`corpus/generator/` if a gate fails — it does not permit fixing `resolver/`
or `corpus/oracle.py` in response to a score, however tempting a single
false negative is to chase. Both gates passed; nothing in `corpus/
generator/` needed fixing. The 0.75 recall stands as reported, per the
whole point of running a held-out set at all.

---

## 65. A prose-only bug in `score_gst.py`'s closing summary, found reading §64's own report, fixed without re-scoring

**Decision.** Reading `corpus/GST_HOLDOUT_RESULTS.md` after §64 landed, its
closing narrative described the flag as scoring "precision 1.0 wherever it
fires" — technically true and materially misleading, since the held-out
result is precision 1.0 / **recall 0.75**, one genuine finding missed. The
narrative-generation code in `corpus/score_gst.py` classified a dataset as
"perfect" on `precision == 1.0` alone, never checking `recall`, and separately
hardcoded "at both seeds" throughout — wrong on a report scoring exactly one
dataset. Both are report-rendering bugs, not scoring bugs: the underlying
`TP`/`FP`/`FN`/`precision`/`recall` numbers in `corpus/gst_holdout_results.json`
were, and remain, exactly right — §64's headline `precision 1.0 / recall 0.75`
was correctly computed and correctly tabled; only the auto-generated prose
paragraph summarizing it was wrong.

**Fixed:** `perfect` now requires `recall == 1.0` too; a new `missed_some`
category (`precision == 1.0`, `recall < 1.0`) gets its own sentence, stated
as a miss, not smoothed into a precision figure; every hardcoded "both
seeds"/dataset-count assumption is replaced with a summary built from
whichever datasets actually fall into which category, by name.

**Regenerated without re-scoring.** `corpus/GST_HOLDOUT_RESULTS.md` was
rebuilt by loading the already-written `corpus/gst_holdout_results.json` and
calling `corpus/score_gst.py::render()` directly on the saved `results` —
not by re-invoking `score_one()`/`resolve()`/`corpus.oracle.score()`. This
matters specifically because of §58: the frozen resolver's CP-SAT enumeration
is not perfectly reproducible run-to-run on a truncating pool, so re-scoring
the held-out dataset a second time — even to fix unrelated prose — could in
principle have produced a different number and silently violated §64's "run
exactly once" claim. Rendering from the saved JSON sidesteps that risk
entirely: the numbers §64 reported are bit-for-bit the numbers in this
corrected document. `corpus/GST_RESULTS.md` (the known-dataset report, never
under a "run exactly once" constraint) WAS re-scored via a normal
`score_gst.py --all` invocation, since no such risk applies there.

**Consequence for §63's freeze.** `corpus/score_gst.py`'s content hash
changes with this fix, breaking §63's literal hash match for that one file.
This is disclosed, not hidden: the file's SCORING logic (`score_one`,
`run_filters`, `precision_recall`, everything the oracle-facing measurement
depends on) is untouched — only `render()`'s narrative-assembly code changed,
after the held-out run, and the held-out run's own recorded numbers were
never regenerated by it. A reader checking §63's hash against the current
file will find a mismatch on `score_gst.py` alone and should read this entry
as the reason, not assume the held-out result was re-run or tuned.

**Scope.** `corpus/score_gst.py` (report-rendering functions only),
`corpus/GST_RESULTS.md` (regenerated by full rerun), `corpus/
GST_HOLDOUT_RESULTS.md` (regenerated from saved JSON, no rerun). No file
under `resolver/`, `resolver_contract/`, `corpus/oracle.py`, or `corpus/
generator/` touched.

---

## 66. The `gstr2b_absent` ITC gap is a DEFECT IN THE CORPUS GENERATOR, not the "structural, not a bug in either side" rounding artefact this repo published — 2026-09-02

**The claim being retracted.** `corpus/score_gst.py::render()` generated, into
both `corpus/GST_RESULTS.md` and `corpus/GST_HOLDOUT_RESULTS.md`, a paragraph
opening:

> **`gstr2b_absent` is the ground that disagrees, structurally — not a bug in
> either side.**

and attributing the disagreement to "the same aggregate-vs-accrued rounding
gap `build_erp_and_gst`'s own `gst_rounding_residuals` already names elsewhere
in this corpus". **Both halves are false**, and the second was refutable
without leaving the file it was printed from.

**How it was found: by arithmetic that did not add up, not by review.** The
three published deltas were

| dataset | true | reported | delta |
|---|---:|---:|---:|
| `datasets_gst/A20_B100_Cmax_gst` | 109574 | 80001 | **+29573** |
| `datasets_gst/A20_B100_Cmax_gst_noisy` | 188218 | 188223 | −5 |
| `datasets_gst_holdout/A20_B100_Cmax_gst_holdout` | 47564 | 47565 | −1 |

Ceiling-rounding per transaction can only make an accrued sum **larger** than
the aggregate, by at most a paise or two per transaction. It explains −5 and
−1 exactly. It cannot produce a **27% one-directional shortfall** on the same
mechanism. The published explanation invoked a quantity whose own recorded
magnitude, three keys away in the same `ground_truth.json`, reads
`{"period": "2027-10", ..., "residual_paise": -1}`. A hostile reader with that
file open needs about ninety seconds.

**The actual mechanism, measured.** The delta has two terms and the identity

```
true − reported  ==  exclusion  +  rounding_residual
```

**holds on every `gstr2b_absent` row of all three datasets.** It is now
computed at render time by `absent_gap_decomposition()` and printed with an
`identity_holds` column, so a future third mechanism shows up as `False`
rather than disappearing into a total.

* **Exclusion (the primary term).** `corpus/generator/build.py:681` builds the
  gateway invoice's taxable value with `row["fee"] - (row["tax"] or 0)`,
  guarded **only** on `fee` being truthy. A payment with `fee > 0, tax == 0` —
  the `gst_applies == False` population minted at
  `corpus/generator/ledger.py:339` (`rng.random() > 0.03`) — therefore
  contributes its **full fee** to the taxable value, and the generator then
  charges 18% on that aggregate. Both consumers exclude those rows:
  `matching/stage4_exceptions.py:121` (`if row["tax"]:`, docstring *"there is
  no input tax on them to claim"*) and `resolver/breaks.py:212`
  (`_accrues_input_tax`). **The consumers are right. Ground truth is wrong.**
* **Rounding (the secondary term).** `gst_rounding_residuals[period]
  .residual_paise` — real, and 1–8 paise, which is all it was ever capable of.

Worked, for the row that exposed it: month `2027-10` contains one row with
`fee = 164298, tax = 0`; `ceil(164298 × 18/100) = 29574`; the month's rounding
residual is `−1`; `29574 + (−1) = 29573` = the delta. The generator's
aggregate taxable base is `608741`, the consumers' is `444443`, and the
difference is `164298` — exactly the untaxed fee. **99.997% of that delta is
exclusion; 0.003% is the rounding the report blamed for all of it.**

**All three sites were read directly, not inferred from a summary:**
`corpus/generator/build.py:681`, `matching/stage4_exceptions.py:121`,
`resolver/breaks.py:212`. `breaks.py`'s own comment asserts the generator's
behaviour to be impossible — *"including their fee in the taxable value would
manufacture a mismatch against an invoice that correctly omits them"*. The
generator's invoice does not omit them. Both sides stated their position in a
code comment; only the **conflict** went unnoticed.

**Why two of three datasets looked innocent, and why that is confirmation
rather than coincidence.** The holdout's −1 and the noisy set's −5 are pure
rounding **only because the seed's dropped invoice happened to land on a month
containing no zero-GST fee row**. The mechanism is live in **9/12, 3/12 and
6/12** settled months of the three datasets respectively. That is now printed
as a coverage table beside the decomposition, because "exclusion term 0" must
not read as "this dataset is unaffected". The diagnosis predicts the holdout
shows no exclusion term, and it does.

**The defect has been visible on SURVIVING invoices all along.**
`analyse_tax`'s `rounding_residuals` reports every month carrying a zero-GST
fee row as out of tolerance by three to four orders of magnitude
(`2027-03`: residual 19486 against a tolerance of 33), and every month without
one as within tolerance by single digits. `gstr2b_absent` is not where the
defect lives — it is the only ground where a **second, independent computation
of the same quantity exists**, so it is the only place the inflation becomes
visible. The disagreement is a detector. Correspondingly, the exact agreement
of `gstr2b_no_irn` and `gstr2b_37a_exposure` is **not** corroboration that
their amount is right: both sides there read the same inflated column.

**Decision: the prose is corrected and the generator is NOT.** What is fixed
here is the false causal claim. `corpus/generator/build.py:681` is recorded as
a defect and left standing on data that already exists.

**Rejected: fix `build.py:681` and regenerate.** `build_erp_and_gst` is shared
by every corpus family, so this moves `gstr2b.csv` and `DATASET_HASHES.txt`
for `datasets/`, `datasets_v2/`, `datasets_bankside/`, `datasets_gst/` **and
`datasets_gst_holdout/`**. Regenerating the held-out family *in response to
having seen its score* is precisely what §63/§64's protocol exists to forbid,
and no amount of "but the fix is correct" repairs a holdout that was
regenerated after the fact. The correct fix belongs to a **future family at
seeds committed before its data exists**, where generator and consumers agree
from the start — the same route `datasets_v2` and `BANKSIDE_POINTS` took.

**Rejected: change the generator's ground truth for `gstr2b_absent` only, to
record the per-transaction accrual.** Two failures. It carries the same
holdout regeneration, and it does not fix the defect — it **defines truth as
whatever the filters compute**, which is the loophole this repository
disciplines against everywhere else. It would also leave the surviving
invoices still inflated and still silently wrong.

**Rejected: change `monthly_fee_accrual` to include zero-GST rows, so the
consumers match the generator.** Barred twice. `matching/` is frozen at
`81c04e0` and `tests/test_holdout_freeze.py` enforces it. And it is
substantively backwards: it would make the recon engine claim input tax credit
on a fee that carried no input tax, contradicting `_accrues_input_tax` and
§61's fix. To a compliance reader that is the more serious of the two errors —
a wrong ITC claim, not a wrong test fixture.

**Rejected: leave the prose and add a footnote.** The sentence "not a bug in
either side" is not incomplete, it is false, and it is the load-bearing
sentence of that section. §62 and §65 are this repository's precedent that a
wrong generated paragraph gets regenerated, not annotated.

**What is and is not affected.** Nothing gated moves. `resolver/breaks.py`
reports month-level ITC-risk flags carrying **no rupee amount**, so §60/§64's
`itc_risk_flag` precision/recall is untouched, and no G-gate reads
`itc_amount_matches`. What was wrong is *published prose about a measured,
ungated number* — which is worse for a hiring artifact than a wrong gate,
because it is the part a reader checks by hand.

**Regenerated without re-scoring the holdout, per §65.**
`corpus/GST_RESULTS.md` was rebuilt by a normal `score_gst.py --all` run.
`corpus/GST_HOLDOUT_RESULTS.md` was rebuilt by the new, committed
`corpus/render_gst_holdout.py`, which loads `corpus/gst_holdout_results.json`
and calls `render()` — it never invokes `score_one()`, `resolve()` or
`corpus.oracle.score()`. §65 did this once ad hoc; committing it makes the
operation repeatable and checkable. The script backfills exactly two
descriptive keys (`absent_gap_decomposition`, `zero_tax_month_coverage`), both
pure functions of committed on-disk data that run no resolver and read no
resolver output, and it **refuses to write if any scored field changed**.
Every held-out number remains bit-for-bit §64's.

**Consequence for §63's freeze, disclosed again.** `corpus/score_gst.py`'s
content hash changes, as it already did under §65. The measurement path this
time is not entirely untouched: `score_one()` gained two calls to the new
descriptive functions. Neither reads a resolver output, neither can alter any
precision/recall/oracle figure, and the held-out JSON was not regenerated by
them. A reader checking §63's hashes will find `score_gst.py` mismatched and
should read §65 and this entry as the reasons.

**Scope.** `corpus/score_gst.py` (two new pure measurement functions, the
`_absent_gap_section()` renderer, and the closing-summary sentence that
repeated the same false claim), the new `corpus/render_gst_holdout.py`,
`corpus/GST_RESULTS.md` and `corpus/gst_results.json` (regenerated by rerun),
`corpus/GST_HOLDOUT_RESULTS.md` and `corpus/gst_holdout_results.json`
(re-rendered from saved JSON, not re-scored), and this entry. **No file under
`corpus/generator/`, `matching/`, `resolver/`, `resolver_contract/` or
`corpus/oracle.py` is touched, and no dataset is regenerated.**

---

## 67. The §58 prediction, committed before the fix — and a correction to §58's own description of the defect — 2026-09-02

**What this entry is.** §58 found that `resolver/enumerate_closures.py`
budgets in wall-clock seconds, documented it, and deferred the fix on the
grounds that it "needs its own dated decision, its own committed-before-the-fix
prediction, and its own before/after pair, exactly as §49 and §50 each got."
This entry and `investigation/resolver_nondeterminism/PREDICTION.md` are that
prediction. **No solver parameter changes in this commit.** The ordering —
prediction, then fix — is the evidence, and it is checkable in `git log`
rather than asserted here.

**§58's description of the defect is wrong, and the correction makes the
defect SMALLER.** §58 records the reproduction as "bank_index=56, both
`Verified`, different composition". Re-running that experiment with every
field of every outcome compared — `investigation/resolver_nondeterminism/
reproduce_58.py`, three `resolve()` calls on the identical in-memory
`Dataset` — **no composition changed on any of the 59 lines.** The only field
that moves is `rival_closure_count`, on exactly the two lines whose
enumeration hit the clock:

```
line 56: Verified  rival_closure_count  167 / 166 / 166
line 58: Verified  rival_closure_count  133 / 130 / 132
```

That is what the code permits: `Verified.composition` comes from `claimed` and
never from `closures`, the enumeration in `_verify` feeds only
`rival_closure_count` and `rival_count_is_lower_bound`, and `Reconstructed`
does not consume — so a truncation cannot propagate through `state.consumed`
into a later tier-B `claimed` set. **The nondeterministic quantity is one the
output already self-declares as a lower bound.** Recorded because a fix whose
writeup overstates what it repaired is the failure mode this file exists to
prevent, and because the correction is *unflattering to the fix*.

**The blast radius is measured, not estimated.** Instrumenting every
`closing_subsets` call across all 35 datasets, uncontended:

```
_tier_c  time_budget_exceeded = 50
_verify  time_budget_exceeded = 26
datasets with ANY clock stop  = 30 / 35
```

`cap_reached` dominates (5–14 per dataset) and is **not** at risk:
`num_workers = 1` with a fixed seed makes CP-SAT's solution order
reproducible, so the first `cap` solutions are identical every run. Only the
76 clock stops are in play. Two sweeps are preserved — one contended, one
clean — on §49's precedent of keeping both draws.

**Two experiments were run before the fix, and one of them falsified the
prediction I had made for it.** Uncontended, three runs each: the two
zero-clock-stop datasets were bit-identical (confirming the `cap_reached`
half), and so was `datasets/A20_Bnone_Cmax` — the *worst* tier-C exposure in
the corpus, which I had predicted would differ. Re-run under six concurrent
resolver processes, the same dataset differs:

```
IDENTICAL ACROSS 3 CONTENDED RUNS: False
  line 11 Unresolved  fields=['detail', 'partial_candidates']
  line 15 Unresolved  fields=['detail', 'partial_candidates']
```

The uncontended result was not evidence of stability; it was evidence that an
idle machine's clock does not vary much. **Both are recorded, including the
miss.**

**The load-bearing finding: the outcome CLASS never flipped**, in any of the
twelve runs across three experiments. What moves is always a descriptive field
of an already-decided line. The mechanism explains why — once the clock stops,
`complete=False` and `_tier_c` returns `Unresolved(ENUMERATION_TRUNCATED)`
unconditionally, so a flip needs a pool that *completes* in one run and not
another, a narrow band; whereas the subset count varies continuously with
available CPU. **`complete` is the stable bit; the count is the unstable one;
only `complete` reaches an outcome class.** This is observed and argued, not
proven, and the prediction flags it as the claim most likely to fail.

**The held-out GST dataset has zero clock stops** — all 54 enumerations return
`optimal`. §58's exposure does not reach it, so `GST_HOLDOUT_RESULTS.md` needs
no re-scoring and §64's single-run claim is not disturbed. This is stated as a
prediction to be *verified* by diffing unfixed against fixed on that dataset,
not as a licence to skip the check.

**The budget.** `max_deterministic_time = 10.0` replacing
`max_time_in_seconds = 10.0`, on §49's reasoning: OR-Tools publishes no
conversion between deterministic units and wall-clock seconds, by design, so
keeping the numeral preserves the order of magnitude without claiming
equivalent search. If the post-fix count of clock stops moves materially in
either direction from 76, the value is revisited rather than accepted — that
would mean the change quietly re-tuned search depth while claiming only to
stabilise it.

**Rejected: fold the prediction into the fix commit.** §49's `PREDICTION.md`
was committed *with* its fix, and that is the weaker precedent — the ordering
then rests on the file's prose rather than on `git log`. §58 explicitly asked
for "committed-before-the-fix". Two commits cost nothing and make the claim
checkable by a reader who trusts no prose at all.

**Rejected: raise `DEFAULT_TIME_BUDGET` instead.** §58 already measured this:
at 60.0s one pool still fails to prove completeness and another merely
converts to `cap_reached`. It trades a five-fold slowdown for the same defect.

**Rejected: predict only "output becomes reproducible" and skip the blast
radius.** That is unfalsifiable in the direction that matters. A prediction
that cannot be wrong about *what moves* provides no check on whether the fix
did something other than advertised.

**Scope.** `investigation/resolver_nondeterminism/` (the prediction, four
measurement scripts, and their outputs) and this entry. **No file under
`resolver/`, `matching/`, `corpus/`, `engine/` or `resolver_contract/` is
touched, and no published figure changes.**

---

## 68. `max_deterministic_time` in `resolver/enumerate_closures.py` — §58's fix, the mislabelled status it exposed, and a published number that was a draw — 2026-09-02

**The change.** `solver.parameters.max_time_in_seconds = time_budget` becomes
`solver.parameters.max_deterministic_time = time_budget` at the single CP-SAT
call site. `DEFAULT_TIME_BUDGET` becomes `DEFAULT_DETERMINISTIC_BUDGET`,
keeping the numeral 10.0 on §49's reasoning — OR-Tools publishes no conversion
between deterministic units and wall-clock seconds, by design, so the numeral
preserves the budget's order of magnitude without claiming equivalent search.
`investigation/resolver_nondeterminism/PREDICTION.md` and §67 were committed
**before** this change existed; `git log` is the evidence.

**A second edit was FORCED, not chosen.** `timed_out` read

```
elapsed >= time_budget and status != cp_model.OPTIMAL
```

comparing an externally measured wall clock against the budget. That is §44's
frame defect, instance F3, retained deliberately as evidence. Under a
deterministic budget the two operands are **not in the same units**, so the
mixture stops being subtle and becomes a type error. §68 does not tidy F3
away; it makes it unstateable. The predicate now compares
`solver.deterministic_time` against `time_budget` — both CP-SAT's own — and a
new `Closures.deterministic_seconds` field records the consumption so the
comparison is auditable from the output rather than re-derived from a clock.
`wall_seconds` is kept, is still honest, and carries an explicit prohibition:
it may inform capacity decisions and may never derive a status or a claim.

**`status == UNKNOWN` alone would NOT have worked, and this was measured.**
A solve that stops on its budget having already found solutions returns
**`FEASIBLE`**, not `UNKNOWN`:

```
enumerate_all_solutions, max_deterministic_time = 0.05
-> status FEASIBLE  found 3114  det_time 0.05000008  wall 0.034455
```

Replacing the wall-clock clause with a status-only test — the obvious
simplification, and the one proposed while this work was in flight — would
have silently relabelled every truncated-with-solutions enumeration as clean.

**Which is not hypothetical: the old predicate was already doing it.**
Across all 35 datasets, before and after:

| status | before | after | delta |
|---|---:|---:|---:|
| `optimal` | 205 | 209 | +4 |
| `cap_reached` | 262 | 275 | +13 |
| `feasible` | **28** | **0** | −28 |
| `time_budget_exceeded` | 69 | 81 | +12 |

Every one of those 28 `feasible` results was a truncated enumeration reported
as if it were not: the external clock came in just under the budget and the
status was `FEASIBLE` rather than `UNKNOWN`, so both disjuncts failed. **This
never reached `complete`** — which is `status == OPTIMAL` and nothing weaker
(§39) — so no line was ever wrongly promoted to a confident answer. But the
status string reached the `detail` text of those outcomes, and an operator
triaging them was reading a wrong word.

**Counted honestly, the fix does MORE search, not less.** True truncations
(`time_budget_exceeded` plus the mislabelled `feasible`) fell **97 → 81**;
`optimal` rose 205 → 209 with **no dataset losing a single one**; the full
35-dataset sweep ran **1410.8s → 1099.3s**. §67's stated trigger for revisiting
the numeral — clock stops moving materially in either direction — is therefore
**not fired**: the apparent +12 is a labelling correction, not a tighter budget.

**The prediction scorecard, including the miss.**

| claim | verdict |
|---|---|
| 1. zero-clock-stop datasets identical, incl. held-out | **FALSIFIED** |
| 2. no outcome CLASS changes anywhere | CONFIRMED — 0 of 35 |
| 3. no composition changes anywhere | CONFIRMED — 0 lines |
| 4. candidate-set statistics move | CONFIRMED, weakly — see below |
| 5. no gate flips | CONFIRMED — 0 flips, 0 gate-count changes, 28/30 passing |
| 6. post-fix runs byte-identical | CONFIRMED — 2 uncontended + 1 contended |

Fields that moved between the pre- and post-fix draws, and nothing else:
`detail` 37, `partial_candidates` 34, `rival_closure_count` 30, `warrant` 5,
`rival_count_is_lower_bound` 4.

**Claim 6 is the one the fix exists for, and it was tested the way the pre-fix
code failed.** Three full 35-dataset outcome dumps — two on an idle machine,
one under six concurrent resolver processes at load average 5.45 — are
byte-identical (`seconds` excluded; wall time varies and its irrelevance to
the ANSWER is the point). Pre-fix, that same contended comparison broke on
`detail` and `partial_candidates`.

**Claim 1 failed, and the reason is worth more than the claim was.** §67
asserted the held-out GST dataset could not be affected because it had "zero
clock stops, all 54 enumerations optimal". That premise was read off **pre-fix
data corrupted by the very defect being fixed**:

```
gst_holdout  before: {feasible: 2, infeasible: 4, optimal: 48}
             after:  {infeasible: 4, optimal: 50}
```

It never had zero truncations. It had two, wearing the `feasible` label. Under
the fix both complete, so `rival_count_is_lower_bound` flips `True → False` on
those lines: the resolver now makes a **stronger and correct** claim where it
previously hedged. No outcome class or composition on that dataset changed. A
measurement taken with a broken instrument is evidence about the instrument.

**Claim 4 is confirmed but the honest form is weaker than the claim.** Against
the previously committed `corpus/oracle_results.json`, `mean`/`max` candidate
set size moved on exactly **1 of 30** datasets. That single dataset is also the
one below whose committed draw disagreed with both of this pass's runs, so the
movement cannot be cleanly attributed to the fix alone. The cleanly attributable
statement is the field-level one: `partial_candidates` differs on 34 lines
between this pass's pre- and post-fix runs.

**A published outcome-class count was a draw, not a measurement — disclosed,
not absorbed.** Re-scoring produced `datasets_v2/A40_B100_Cfifo` at
`Ambiguous 1 / Unresolved 7`, where the committed `oracle_results.json` said
`Ambiguous 2 / Unresolved 6`. This is **not** the fix: this pass's own pre-fix
and post-fix dumps agree with each other at 1/7, and disagree with the
committed file. The committed number was an older draw of the nondeterministic
pre-fix code — §58's defect, live in a published figure, exactly as §58 warned
("a claim about one draw"). The corrected figure now stands, and the previous
one is recorded here rather than quietly replaced. No gate verdict moves with
it; the dataset passed before and passes now.

**The frozen-cascade baseline was deliberately NOT re-run.**
`corpus/baseline_old_engine.py` drives `matching/`, which this change does not
touch — verified by `git status matching/ engine/` returning empty, not by
memory — and §49 already made that path deterministic. Re-running it costs ~43
minutes for a provably byte-identical `corpus/baseline_results.json`. The
skip is recorded so a reader does not conclude the step was forgotten.

**`corpus/GST_HOLDOUT_RESULTS.md` was NOT re-scored, and claim 1's failure is
the reason.** The resolver *would* now answer differently on that dataset. That
makes re-running §64's single held-out run more dangerous, not less. It stays
rendered from saved JSON per §65; the divergence is disclosed here instead.

**A defect in this pass's own new code, caught by the contract.** §69's
`composition_cardinality()` was first written with
`getattr(outcome, "composition", None)` — the obvious defensive spelling. It
does not work: `Ambiguous.__getattr__` raises `UnrepresentableClaim`, a
`ContractViolation` and **not** an `AttributeError`, so `getattr`'s default
never fires and the exception propagated and killed the re-score. Asking an
ambiguous outcome for a composition is a bug and `resolver_contract` refuses to
let a default paper over it. Fixed to `isinstance(outcome, (Verified,
Reconstructed))`. Recorded because the contract catching its own author, in the
pass that adds a legibility section, is the clearest evidence that
`model.py`'s "unrepresentable rather than discouraged" design earns its keep.

**Rejected: raise the numeral now that more enumerations complete.** Tempting,
and it would be tuning. §67 fixed the numeral in advance precisely so this pass
could not drift, and nothing measured shows 10.0 too small — `optimal` went up.

**Rejected: delete `wall_seconds`.** Not a misnomer; it measures wall time and
is the right field for capacity questions. The defect was deriving a *claim*
from it. Removing it would also destroy the number showing the fix runs faster.

**Rejected: re-run the whole `run_all.py` including the baseline, for tidiness.**
A 43-minute step whose output cannot change is not rigour, it is ceremony, and
recording the reasoning is more auditable than the runtime.

**Scope.** `resolver/enumerate_closures.py` (the parameter, the constant name,
the `budget_exhausted` derivation, the new `deterministic_seconds` field),
`investigation/resolver_nondeterminism/` (before/after pair, three verification
runs, four measurement scripts), and the regenerated
`corpus/ORACLE_RESULTS.md`, `corpus/oracle_results.json`,
`corpus/THREE_SYSTEMS.md`, `CLAIMS.md`, `SCORECARD.md` and
`dashboard/data.json`. No file under `matching/`, `engine/`,
`corpus/generator/`, `resolver_contract/` or `corpus/oracle.py` is touched, and
no dataset is regenerated.

**`corpus/GST_RESULTS.md` is NOT regenerated in this commit, and the reason is
a concurrency hazard rather than a decision about GST.** A separate, concurrent
line of work modified `resolver/loaders.py` at 01:14 (a `paise()` grammar fix
from the adversarial pass). This pass's evidence is unaffected -- every
before/after and verification dump was written between 22:27 and 00:52, and
`corpus/oracle_results.json`'s process imported `loaders.py` at ~00:56, all
before that edit. But `corpus/score_gst.py` runs as a LATER process and would
have imported the modified loader, so its output would carry two independent
changes under one entry's name. That is exactly the mixing this file exists to
prevent, so the GST re-score is deferred to a pass that owns the loader change
and can attribute its effect separately. `corpus/GST_RESULTS.md` therefore
still reflects §66's regeneration, taken under the pre-§68 wall-clock budget;
the resolver-derived figures in it are one draw and are superseded whenever
that pass runs.

---

## 69. Composition cardinality — the one thing a reconciliation professional asks first, which this repo's output could not answer — 2026-09-02

**Decision.** `corpus/score_resolver.py` gains `composition_cardinality()` and a
report section splitting every answered bank line into **1:1** (one credit, one
row) and **N:1** (one credit, several rows netted), broken down by outcome
class, plus a count of lines whose composition carries at least one DEBIT row.
`corpus/TECHNIQUES.md` assessed this as "adopt, reporting only, cheap, no
contract change" and it was never built.

**Why it is worth a numbered entry when it introduces no new measurement.**
Every figure is a re-cut of outcomes the oracle already scores. The problem it
solves is not measurement, it is **legibility to the reader this artifact is
for**. `Verified 275, mean candidate set size 3.4` is a sentence in this
repository's private dialect. A reconciliation practitioner reads an engine in
cardinalities, and their first question is *how much of this was one-to-one?* —
because a 1:1 match is what a `GROUP BY` on a shared key already solves, and
this repo has measured that a fifteen-line `GROUP BY` recovers 322 of 335
compositions. Reporting a strong headline without the split invites it to be
read as a claim about the hard cases. The split is what makes the claim honest
at a glance rather than after reading `THREE_SYSTEMS.md`.

**N:N is reported as 0 BY CONSTRUCTION, and labelled as such.**
`ResolverOutput` carries exactly one outcome per bank line, so no answer can
span two credits. An unexplained `0` in a table reads as "measured, none
found"; this one is a **design boundary**, and a reader comparing against an
engine that re-groups bank lines needs to know the difference. §2's rejection
of a global set-partitioning formulation (1,347 booleans returning UNKNOWN at
60s) is why the boundary exists.

**Split by outcome class rather than pooled.** A 1:1 `Verified` — two
independent parties agreeing on a composition — and a 1:1 `Reconstructed` —
this resolver's own arithmetic with no second party attesting anything — are
different evidential objects. Pooling them would undo exactly the distinction
the contract's tiers exist to draw, in a table whose purpose is to make the
output easier to read.

**`with_debits` is included because it is the narrowest honest measure of what
netting bought.** It counts answered lines whose composition carries at least
one debit — a refund or adjustment netted against credits inside the same
payout. Those are the lines where a credits-only sum would have produced the
wrong figure. `N:1` alone overstates the case: a multi-row credit-only batch is
still just a sum.

**Rejected: put this in `SCORECARD.md` instead.** `SCORECARD.md` is generated
from `corpus/scorecard.py` and is the five-minute read; adding a fourth table
to it dilutes the thing it is for. `score_resolver.py`'s report is where
per-dataset detail already lives.

**Rejected: derive cardinality from ground truth rather than from output.**
It would be a statement about the corpus, not about the resolver, and the
question being answered is what the ENGINE produced.

**Rejected: report a mean composition size.** A mean over a bimodal
distribution (mostly 1, occasionally 30) describes neither mode. The two
buckets are the honest summary.

**Scope.** `corpus/score_resolver.py` (two new functions, one report section)
and this entry. No contract change, no corpus change, no scoring change — the
oracle's inputs and outputs are untouched.
