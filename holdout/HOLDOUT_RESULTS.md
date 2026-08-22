# HOLDOUT_RESULTS.md — cold run of the frozen cascade

Produced by `eval/holdout_report.py`. Solver frozen at `81c04e0` and
**not modified in response to anything below**. Metric definitions are
`DECISIONS.md` §12, unchanged, so the two columns are comparable.

Data: `holdout/`, seed `20260905`, committed before generation.
Period 2026-09-14 .. 2026-11-27. 240 rows, 18 bank lines (3 of them debits, a shape the engine had never seen).

## 1. Headline

| metric | primary | **held-out** | delta |
|---|---:|---:|---:|
| match rate | 96.55% (196/203) | **73.11%** (155/212) | -23.44 pp |
| precision (determinate batches) | 1.0000 | **0.7863** | -0.2137 |
| recall (determinate batches) | 1.0000 | **1.0000** | +0.0000 |
| rows placed in the wrong batch | 0 | **50** | +50 |
| rows placed that should not settle | 0 | **0** | +0 |
| balance-identity violations | 0 | **0** | +0 |
| ambiguous batches flagged | 3 | **4** | +1 |
| **mean candidate set size** | 2.00 | **8.75** | +6.75 |
| truth in candidates, every batch | True | **False** | |
| wall clock (mean of 3) | — | **10.45s** | |

## 2. Row accounting — the same three buckets

Disjoint, and asserted to partition all 240 rows (`partitions == True`).

| bucket | primary | held-out |
|---|---:|---:|
| truly settled — placed correctly | 196 | 155 |
| truly settled — placed **incorrectly** | 0 | 50 |
| truly settled — declined, provably ambiguous | 7 | 7 |
| truly settled — missed | 0 | 0 |
| truly unsettled — correctly left unmatched | 37 | 28 |
| truly unsettled — **wrongly placed** | 0 | 0 |

### The excluded denominator, itemised

| true reason | primary | held-out |
|---|---:|---:|
| `debit_deferred_past_horizon` | 5 | 0 |
| `netted_out_by_full_refund` | 14 | 12 |
| `not_captured` | 4 | 4 |
| `on_hold_dispute` | 5 | 6 |
| `rolled_forward_past_horizon` | 9 | 6 |

## 3. Ambiguity handling

- planted, provably unresolvable batches: **3**
- detected: **3** (recall 100%)
- missed: **0**
- additional batches flagged: **1**
- true decomposition present among the candidates on every batch: **False**
- enumerations truncated at the cap: **0**

### Mean candidate set size — reported unprompted

`truth_in_candidates` is gameable on its own: a solver returning all
2ⁿ subsets contains the truth every time and has decided nothing. The
candidate set size is what closes that loophole, so it is reported
beside the pool it was drawn from rather than left to be asked for.

| | primary | held-out |
|---|---:|---:|
| ambiguous bank lines | 3 | 4 |
| **mean candidate set size** | **2.00** | **8.75** |
| min / max | 2 / 2 | 2 / 29 |
| mean pool size those were drawn from | 23.3 rows | 27.0 rows |

The engine narrows a 27-row pool to 8.75 candidates on average and then **refuses to choose between them**. That is the claim the number defends.

## 4. The reversals — prediction vs outcome

The pre-registered prediction is `holdout/HOLDOUT_SPEC.md` §3, committed
before this script was ever run. Verify with `git log --reverse`.

### 4.1 Scorecard — 6 of 7 predictions held

Computed from the run, not typed in.

| # | prediction | outcome | verdict |
|---|---|---|:-:|
| **P1** | the reversal DEBIT is not joined by stage 1 or 2 | 0 of 3 debits joined | HELD |
| **P2** | the ORIGINAL credit A is not joined by stage 1 or 2 | 0 of 3 joined | HELD |
| **P3** | stage 3 places rows into credit A anyway -> placed_incorrectly, NOT routed to exceptions (the brief predicted exceptions) | 3/3 credit-A lines resolved Determinate; 3/3 took rows; 50 reversal rows scored placed_incorrectly | HELD |
| **P4** | credit B is damaged in turn -- its rows were already consumed | 3 of 3 credit-B lines failed to reconstruct their true rows | HELD |
| **P5** | the reversal debit may be ABSORBED into a spurious decomposition | 0 of 3 debits absorbed; the rest resolved Unresolved | **FALSIFIED** |
| **P6** | no balance-identity violation | 0 violations | HELD |
| **P7** | match rate falls below the primary's and precision below 1.000 | match rate 73.11% vs 96.55%; precision 0.7863 vs 1.0000 | HELD |

**P5 was wrong, and it is reported as wrong.** Predicted: the reversal debit may be ABSORBED into a spurious decomposition. Actual: 0 of 3 debits absorbed; the rest resolved Unresolved.

### 4.2 The headline finding of Task 2

**The brief's expectation was wrong, and so was part of mine.**

The brief expected the engine to route the affected rows to exceptions.
It does not. It places them into the *original* credit A with a closing
arithmetic proof and full confidence, and the ground truth says they
belong to the re-settlement B. That is a **confident wrong answer**, the
failure mode the phase brief named as the one to watch for, and it is
what actually happened on all three planted reversals.

The engine has **no representation for a bank credit that was later
revoked**. Stage 3 walks bank lines in date order and asks, of each, 
"which pool rows net to this amount?" At credit A's date the honest
answer is *those rows* — they genuinely did compose that credit, and the
credit genuinely posted. The engine is not hallucinating; it is answering
a question that has no memory of revocation in it. Detecting the reversal
requires relating a *later* debit back to an *earlier* credit, which is
state the cascade never carries.

A second-order cost, which is the part that would hurt in production: 
because credit A resolves `Determinate` and carries no attestation, `stage3_solver.run` takes the `elif` branch and **consumes** those rows.
Credit B then reconstructs from a pool its own rows are missing from — so
one reversal damages **two** bank lines, not one. On `bank[9]` that
surfaces as an ambiguity with 29 candidates where the true decomposition
is not even among them.

**What the engine DID get right, and it is not nothing.** The reversal
debits themselves are not absorbed (P5 falsified): all 3 resolve `Unresolved` and reach the exception queue
as `genuinely_unresolved`, along with the damaged credit-B lines — 5 bank lines in total (`[4, 5, 8, 13, 14]`), against 0 on the primary set. So the engine
does raise its hand about the **bank lines** it cannot explain. What it
does not do is revisit the **rows** it already placed with confidence.
The queue says "I cannot explain these three debits"; it does not say
"...and therefore my earlier answer about credit A is void."

**The reversal is also expensive.** Held-out wall clock is 10.45s against the primary's ~1.4s, and
almost all of it is one line: the contaminated `bank[9]` takes 9.43s
alone, enumerating 29 candidates over a 33-row pool because the rows that
would have closed it exactly were consumed by credit A. A pool polluted
by an unrecognised reversal is both slower and less decisive — the two
costs arrive together.

### 4.3 How much of the drop is the unseen class

**A diagnostic, not the headline.** The headline stays 73.11% — an
engine does not get to exclude the cases it failed. This answers the
separate question of whether the drop is the new class or a general
regression, and it is only a fair question to ask because the
attribution turned out to be total:

- rows placed incorrectly: **50**
- of those, rows belonging to a reversed batch: **50**
- rows placed incorrectly that are NOT reversal-related: **0**

| | primary | held-out, all rows | held-out, reversal rows excluded |
|---|---:|---:|---:|
| match rate | 96.55% | **73.11%** | 95.68% |
| placed correctly | 196 | 155 | 155 |
| placed incorrectly | 0 | 50 | 0 |
| declined as ambiguous | 7 | 7 | 7 |
| missed | 0 | 0 | 0 |

On the fifteen classes the engine HAS seen, held-out behaviour is
indistinguishable from primary: **0 rows placed
incorrectly**, **0 missed**, and the same
7 rows declined on proven ambiguity. The engine did
not degrade on unseen data drawn from classes it knows — it failed on
**one class it had never encountered**, and it failed by being
confident rather than by being silent.

The honest reading of both numbers together: the cascade generalises
across draws, and has a **specific, named, reproducible gap** that a
held-out set was the only way to find. Neither half of that sentence is
worth much without the other.

### 4.4 Per-reversal detail

### `1791372600osmYw6` → `17919774000n3xCG` (7 rows, ₹23,060.17)

| bank line | index | joined by stage 1/2 | stage 3 outcome |
|---|---:|:-:|---|
| credit A (original) | 3 | False | Determinate (7 rows) |
| DEBIT (the return) | 4 | False | Unresolved |
| credit B (re-settlement) | 5 | True | Unresolved |

- rows placed by the engine: **7 → bank[3]**
- rows declined as contested: 0
- rows left unplaced entirely: 0
- rows appearing in the exception queue: 1

### `1792582200GqaPVy` → `1793187000FQuOA5` (22 rows, ₹82,534.96)

| bank line | index | joined by stage 1/2 | stage 3 outcome |
|---|---:|:-:|---|
| credit A (original) | 7 | False | Determinate (22 rows) |
| DEBIT (the return) | 8 | False | Unresolved |
| credit B (re-settlement) | 9 | True | Ambiguous (29 candidates) |

- rows placed by the engine: **22 → bank[7]**
- rows declined as contested: 1
- rows left unplaced entirely: 0
- rows appearing in the exception queue: 2

### `1794396600LGOvuF` → `17950014003XVRBM` (21 rows, ₹84,626.01)

| bank line | index | joined by stage 1/2 | stage 3 outcome |
|---|---:|:-:|---|
| credit A (original) | 12 | False | Determinate (21 rows) |
| DEBIT (the return) | 13 | False | Unresolved |
| credit B (re-settlement) | 14 | True | Unresolved |

- rows placed by the engine: **21 → bank[12]**
- rows declined as contested: 2
- rows left unplaced entirely: 0
- rows appearing in the exception queue: 1

## 5. Exception queue, itemised

| type | primary | held-out | owner | actionable |
|---|---:|---:|---|:-:|
| `ambiguous_batch_membership` | 7 | 7 | finance-ops | yes |
| `deferred_debit_pending` | 2 | 0 | treasury | yes |
| `dispute_hold_pending` | 5 | 6 | disputes-ops | yes |
| `erp_gap_no_order` | 14 | 14 | finance-ops | yes |
| `erp_gap_no_payment` | 6 | 6 | finance-ops | yes |
| `failed_payment_never_settles` | 4 | 4 | no-action | no |
| `genuinely_unresolved` | 0 | 5 | finance-ops | yes |
| `gstr2b_37a_exposure` | 1 | 1 | tax-ops | yes |
| `gstr2b_absent` | 1 | 1 | tax-ops | yes |
| `gstr2b_no_irn` | 1 | 1 | tax-ops | yes |
| `lost_dispute_adjustment` | 4 | 4 | finance-ops | yes |
| `netted_out_by_full_refund` | 14 | 12 | no-action | no |
| `subset_sum_rolled_forward` | 9 | 6 | no-action | no |

**45 actionable** of 67 total (primary: 41 of 68).

## 6. False-positive audit

| check | primary | held-out |
|---|---:|---:|
| ERP-gap payments wrongly given an invoice | 0 | 0 |
| orphan ERP invoices wrongly given a payment | 0 | 0 |
| adjustment rows given a counterparty | 0 | 0 |
| Hungarian pairs proposed | 6 | 6 |
| Hungarian pairs refused | 6 | 6 |
| Hungarian assignments accepted | 0 | 0 |
| fuzzy pairs proposed then refused | 1 | 0 |

## 7. Runtime and determinism

| | seconds |
|---|---:|
| stage1 | 0.000 |
| stage2 | 0.000 |
| stage3 | 10.484 |
| stage4 | 0.001 |
| total | 10.486 |

Mean wall clock over 3 runs: **10.45s** (min 10.39s, max 10.49s).
Slowest single bank line: `bank[9]` at 9.43s over a 33-row pool.
Bank lines over the 30s per-credit budget: **0**.

**Determinism:** 3 consecutive runs on held-out data.

- run 1: `6b811ef955b3a538`
- run 2: `6b811ef955b3a538`
- run 3: `6b811ef955b3a538`

Identical across all runs: **True**

