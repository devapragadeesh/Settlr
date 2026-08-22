# HOLDOUT_SPEC.md — the held-out set, the reversal extension, and the prediction

**Status:** normative for `holdout/` only. Nothing here changes
`engine/SETTLEMENT_SPEC.md`, the frozen dataset, or `matching/`.

**Purpose.** Every number in `eval/EVAL_REPORT.md` was measured on data this
project built. This directory exists to convert *"these numbers came from data
I built"* into *"these numbers came from data the engine had never seen."*

---

## 1. What is held out, and what is not

| | primary (`engine/`) | held-out (`holdout/`) |
|---|---|---|
| seed | `20260822` | `20260905`, committed before generation |
| ledger period | 2026-06-15 .. 2026-08-28 | **2026-09-14 .. 2026-11-27** |
| cut-offs | 12 weekly, 06-17 .. 09-02 | 12 weekly, **09-16 .. 12-02** |
| generator | `engine/generator.py` | `engine/generator.py`, **byte-identical** |
| classes | 15 | 15 **+ `h01` reversals** |
| solver | frozen at `81c04e0` | frozen at `81c04e0`, **unchanged** |

The periods do not overlap: the held-out ledger opens twelve days after the
primary ledger closes, and its first cut-off falls after the primary's last. No
timestamp, entity id, invoice number or UTR can be shared by accident.

**What is NOT held out, stated so it is not overclaimed.** The *generator* is
shared, so both sets are drawn from the same distribution. This measures
generalisation across draws, not across data-generating processes — a
sterner test would be a dataset built by someone else, which does not exist for
this problem. What it does rule out is the specific failure it was built to
rule out: an engine tuned to the particular 240 rows in `engine/data/`.

**How the frozen generator produces a different period without being edited.**
`holdout/generate_holdout.py` imports it as a library and rebinds
`WINDOW_START`, `WINDOW_END` and `BATCH_DATES` **on the imported module object**
for the life of the process. The file on disk is never written.
`tests/test_holdout_freeze.py` hashes `engine/generator.py` before and after a
generation run and asserts equality, so this is a checked property rather than
a claim.

---

## 2. The unseen class: `h01_settlement_reversal_resettled`

**Provenance tier: `synthesized_modelled`.** Razorpay documents no reversal or
failed-payout behaviour anywhere this project could find, and
`SETTLEMENT_SPEC.md` §10 says so explicitly. Nothing below is claimed to be
observed Razorpay behaviour. It is the standard aggregator/bank mechanism.

**The mechanism.**

1. A batch settles normally. A bank **credit** is posted under **UTR-A**.
2. The payout later **fails at the bank** — invalid account, closed account,
   beneficiary name mismatch — and the bank raises a NEFT return.
3. A bank **DEBIT** appears reversing that credit, **referencing UTR-A** in its
   narration, two calendar days after the credit.
4. The same rows **re-settle in a later batch under a NEW UTR-B**, at the next
   weekly cut-off.

**This is a bank-statement shape the primary set does not have**, in two ways
that matter independently:

- a **debit line** — every bank line in `engine/data/bank_statement.csv` is a
  credit, so a negative `amount` has never reached the cascade;
- a **credit whose composition duplicates an earlier credit's** — the same rows
  net to the same amount under two different UTRs on two different dates.

**Where the rows point.** The ledger rows move from settlement A to the new
settlement B, because `recon_combined.json` is a current-state snapshot and B
is the settlement that actually paid them. Settlement A is retained in the
ground-truth key, marked `reversed_by`, because it genuinely occurred and was
genuinely reversed. *Rejected: leaving the rows attesting UTR-A.* That makes
the re-settlement invisible to any consumer of the recon file, which is not how
a merchant sees it, and it would have made the engine's job easier rather than
harder.

**Three reversals are planted.** The exclusions on which batches may carry one
— last two batches, blanked-UTR row, ambiguous batches, month-crossing
re-settlements — are documented with the direction of each bias in
`_eligible_for_reversal`. The two substantive ones: excluding ambiguous batches
keeps `h01` separable from `c07` and makes the case **cleaner, i.e. easier**;
excluding month-crossing re-settlements keeps monthly fee accrual — and
therefore `gstr2b.csv` — untouched, so the reversal is a single isolated
variable rather than a tax finding in disguise.

---

## 3. THE PREDICTION — written and committed before the engine was run

This section was committed **before** `eval/holdout_report.py` was executed
against `holdout/`. The commit ordering is the evidence. **A written
prediction that turns out wrong, reported honestly, is worth more than a
correct one recorded after the fact**, and §4 of `holdout/HOLDOUT_RESULTS.md`
reports what actually happened either way.

### 3.1 The expectation stated in the phase brief

> The engine **cannot match the reversal debit** (no stage handles it) and
> **routes the affected rows to exceptions** rather than mismatching them or
> producing a balance violation.

### 3.2 My prediction, which agrees with the first half and DISAGREES with the second

Reading the frozen cascade before running it, I predict the first clause holds
and **the second clause fails**. Specifically:

| # | prediction | confidence |
|---|---|---|
| **P1** | The reversal **debit** is not matched to any settlement by Stage 1 or Stage 2. Stage 1 joins `settlement_id → UTR` and no ledger row attests UTR-A any more; Stage 2 needs an open batch within tolerance on `(amount, date)` and a negative amount matches none. | high |
| **P2** | The **original credit A** is likewise unjoined by Stages 1–2, for the same reason: its UTR is attested by nothing after the rows move to B. | high |
| **P3** | **Stage 3 will place rows into credit A anyway, and this will be scored as `placed_incorrectly` — NOT as an exception.** `stage3_solver.run` iterates *every* bank line in date order and reconstructs from the pool. At credit A's date the rows are eligible, unconsumed, and net exactly to A's amount, because they genuinely did. The engine returns a confident `Determinate`. Truth says those rows belong to B. | **high — this is the disagreement** |
| **P4** | Because credit A resolves `Determinate` and has no `bank_to_batch` entry, `run()` takes the `elif` branch and **consumes those rows**. By the time credit B is reached its own rows are gone from the pool, so **credit B resolves `Unresolved` or picks up unrelated rows**. One reversal therefore damages *two* bank lines. | medium-high |
| **P5** | The reversal **debit may be absorbed**: `enumerate_decompositions` is given a negative target, and a subset of refund/adjustment rows nets negative, so a spurious "decomposition" of the return leg is available. If it fires, rows are consumed by an event that moved no money. | medium |
| **P6** | **No balance-identity violation.** `Determinate.__post_init__` raises unless the arithmetic closes, so a wrong answer here is wrong about *which* rows, never about the sum. `balance_violations()` stays empty. | high |
| **P7** | Match rate on the held-out set falls **below** the primary's 96.55%, by roughly the number of rows in the three reversed batches, and **precision falls below 1.000** — the first time it has. | medium-high |

### 3.3 Why I expect the brief's version to be wrong

The brief's expectation assumes the engine has a *representation* for "a bank
credit that was subsequently reversed" and will fall through to Stage 4 for
want of one. It has no such representation. Stage 4 receives exceptions for
rows the earlier stages left over; it is not consulted about a bank line that
Stage 3 confidently explained. The engine's failure mode here is not silence —
it is **confidence about a credit that was later undone**, which is the more
dangerous of the two and the one worth surfacing to a panel.

Note what the engine gets *right* even so: credit A really did pay exactly
those rows on exactly that date. The engine's answer was true when the credit
posted. What it lacks is any notion that a later debit can revoke an earlier
credit — reconciliation state that is not derivable from a single pass over
lines in date order.

### 3.4 What would falsify each prediction

- **P1/P2 falsified** if either line appears in `bank_to_batch`.
- **P3 falsified** if the affected rows appear in the exception queue rather
  than in `stage3.assigned` — which is the brief's expectation, and would mean
  the cascade is more conservative than I read it to be.
- **P4 falsified** if credit B resolves `Determinate` with its true rows.
- **P5 falsified** if the debit line resolves `Unresolved`.
- **P6 falsified** by any non-empty `balance_violations()`. This is the one
  that would be a genuine bug rather than a missing feature, and the phase
  constraint is to stop and ask rather than patch it.
- **P7 falsified** if held-out match rate and precision match the primary's.

---

## 4. What this phase may and may not change

**May not**, under any held-out result: `matching/` (frozen at `81c04e0`),
`engine/data/`, `engine/ground_truth/`, `engine/simulator.py`,
`engine/generator.py`, `engine/DATASET_HASHES.txt`, the held-out seed.

If the engine does worse, **that is the finding and it is reported as the
headline.** Tuning the cascade until the held-out numbers improve destroys the
only thing a held-out set is for.

**May**: add new files under `holdout/`, `scale/` and `eval/`, and record
findings in `DECISIONS.md`.
