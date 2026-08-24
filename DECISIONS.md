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
