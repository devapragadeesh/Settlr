# EVAL_REPORT.md

Produced by `eval/report.py` from a live run against the frozen dataset
(commit `f7a6450`). LLM leg: **deterministic**.

## Headline

| metric | value |
|---|---:|
| **match rate** | **96.55%** (196/203) |
| precision (determinate batches) | 1.0000 |
| recall (determinate batches) | 1.0000 |
| rows placed in the wrong batch | 0 |
| rows placed that should not settle at all | 0 |
| balance-identity violations | 0 |
| ITC at risk | ₹2,784.02 |
| wall clock (mean of 3 runs) | 1.37s |

**Not 100%, and it should not be.** 7 rows sit in batches the engine proved ambiguous and declined to guess at; 37 rows correctly have no bank credit at all. Both are reported below rather than absorbed into the numerator. The exceptions are the product.

## Row accounting

Disjoint on the settlement axis -- every row lands in exactly one bucket,
and they sum to 240 (`partitions == True`). ERP and GST findings are a
SEPARATE axis: a payment can be correctly matched to its bank credit and
still have no ERP order, so those are not counted here.

| bucket | rows |
|---|---:|
| truly settled -- placed correctly | 196 |
| truly settled -- placed **incorrectly** | 0 |
| truly settled -- declined, batch provably ambiguous | 7 |
| truly settled -- missed | 0 |
| truly unsettled -- correctly left unmatched | 37 |
| truly unsettled -- **wrongly placed** | 0 |

### The excluded denominator, itemised

These rows have no bank credit to find. Matching one would be a false
positive, so counting them as misses would penalise the engine for being
right. Excluded from the match-rate denominator and listed in full:

| true reason | rows |
|---|---:|
| `debit_deferred_past_horizon` | 5 |
| `netted_out_by_full_refund` | 14 |
| `not_captured` | 4 |
| `on_hold_dispute` | 5 |
| `rolled_forward_past_horizon` | 9 |

## Stage-by-stage contribution

Each stage sees only what earlier stages could not resolve, so these are
cumulative and a stage's own contribution is the increment.

| stage | bank lines resolved | cumulative |
|---|---:|---:|
| Stage 1 exact join (`settlement_id` -> UTR) | 10 | 10/12 |
| Stage 2 fuzzy fallback (`amount`, `date`) | 2 | 12/12 |

Stage 1 leaves two bank lines unjoined, and they fail for **different**
reasons that look identical from Stage 1:

- `bank[10]` -- recovered on (amount, value_date); bank utr column blank; amount delta 0 paise, 0 day(s); narration similarity 94.3
- `bank[11]` -- recovered on (amount, value_date); ledger settlement_utr null (adjustment-only batch); amount delta 0 paise, 0 day(s); narration similarity 88.9

| Stage 3 outcome | bank lines |
|---|---:|
| determinate, arithmetic closes | 9 |
| ambiguous, more than one valid decomposition | 3 |
| unresolved | 0 |

Stage 3 reconstructs every bank credit from scratch with the settlement
columns withheld, so it does not merely restate Stage 1: it is the only
stage that can DISAGREE with the recon file, and it does -- see below.

## The ambiguity contract

- planted, provably unresolvable batches: **2**
- detected: **2** (recall 100%)
- missed: **0**
- additional batches flagged: **1**
- true decomposition present among enumerated candidates on every batch: **True**
- enumerations truncated at the cap: **0**

### On the additional flag

`setl_nXePRBtWmHMwcp` is reported ambiguous although the
ground-truth key marks it determinate. **This is not a false positive.**
The key records ambiguity as the simulator defined it -- ties among
subsets achieving the maximum sum under the live-balance cap. The engine
asks a different and stricter question: given only the bank credit and
the pool available that day, is there more than one subset that nets to
it? For this batch there are two, and the engine enumerates both. A
reconstructor that named one would be asserting something it cannot
know. Declining is the correct answer to the question actually asked.

For every ambiguous batch the engine returns an `Ambiguous` value, which
**has no `decomposition` attribute at all**. There is no field to read and
no flag to forget to check: a confident single answer is unrepresentable
rather than discouraged. See `matching/model.py`.

## False-positive audit

A matcher that pairs everything scores 100% recall and is worthless.
These are the checks that separate the two.

| check | result |
|---|---:|
| ERP-gap payments wrongly given an invoice | 0 |
| orphan ERP invoices wrongly given a payment | 0 |
| adjustment rows given a counterparty | 0 |
| Hungarian assignments made | 0 |
| Hungarian pairs proposed then refused | 6 |
| fuzzy pairs proposed then refused | 1 |

The ERP gaps are REAL gaps. Blocking proposes candidates on amount and
date; the gate refuses every one for want of a shared identifier. An
engine that never looked and an engine that looked and refused produce the
same empty assignment, so the refusals are counted.

## Exception queue, itemised

| type | count | owner | actionable |
|---|---:|---|:-:|
| `ambiguous_batch_membership` | 7 | finance-ops | yes |
| `deferred_debit_pending` | 2 | treasury | yes |
| `dispute_hold_pending` | 5 | disputes-ops | yes |
| `erp_gap_no_order` | 14 | finance-ops | yes |
| `erp_gap_no_payment` | 6 | finance-ops | yes |
| `failed_payment_never_settles` | 4 | no-action | no |
| `gstr2b_37a_exposure` | 1 | tax-ops | yes |
| `gstr2b_absent` | 1 | tax-ops | yes |
| `gstr2b_no_irn` | 1 | tax-ops | yes |
| `lost_dispute_adjustment` | 4 | finance-ops | yes |
| `netted_out_by_full_refund` | 14 | no-action | no |
| `subset_sum_rolled_forward` | 9 | no-action | no |

**41 actionable** of 68 total. The rest are correct, expected
states -- classified and reported so they are visibly accounted for
rather than quietly inflating either the match rate or the queue.

## Tax leg

The gateway's GSTIN is not labelled anywhere in the data. It is
identified as `29FHBXN9205D1ZV` by tying 2B invoice taxable values
to the fee actually deducted, month by month -- the way an accountant
would, not by assumption.

| period | taxable accrued | tax accrued |
|---|---:|---:|
| 2026-06 | ₹1,348.72 | ₹242.88 |
| 2026-07 | ₹7,966.63 | ₹1,434.34 |
| 2026-08 | ₹6,149.34 | ₹1,107.20 |

**Fee charged without GST:** ₹425.66 across 6 rows. No input tax on these, so
they are excluded from the invoice taxable value rather than inflating it.

**GST rounding residuals.** A consolidated invoice computes GST once on
the monthly aggregate; the ledger accrues ceiling-rounded tax per
transaction. The gap is real and is reported, not forced to match.

| period | invoice | accrued tax | invoiced tax | residual | within tolerance |
|---|---|---:|---:|---:|:-:|
| 2026-06 | `RZP/BLR/26-27/7000` | 24288p | 24278p | -10p | True |
| 2026-08 | `RZP/BLR/26-27/7002` | 110720p | 110690p | -30p | True |

**Total ITC at risk: ₹2,784.02**, on three distinct
statutory grounds:

| ground | provision | ITC |
|---|---|---:|
| `gstr2b_absent` (2026-07) | Sec 16(2)(aa) CGST | ₹1,434.34 |
| `gstr2b_37a_exposure` (2026-06) | Rule 37A CGST | ₹242.78 |
| `gstr2b_no_irn` (2026-08) | Rule 48(5) CGST | ₹1,106.90 |

The Rule 37A line is the one worth pointing at: GSTR-2B still reports
`itc_availability: Yes` for it. The exposure is invisible in the return
and has to be COMPUTED from the supplier's filing status.

## Runtime and determinism

| stage | seconds |
|---|---:|
| stage1 | 0.000 |
| stage2 | 0.000 |
| stage3 | 1.357 |
| stage4 | 0.001 |
| total | 1.359 |

Slowest single bank credit: `bank[3]` at 1.28s over a 27-row pool. Within the 30s per-credit budget; any breach is reported, never
silently swapped for an approximate method.

**Determinism:** 3 consecutive runs, LLM leg `deterministic`.

- run 1: `c6ef6cd9bdd95039`
- run 2: `c6ef6cd9bdd95039`
- run 3: `c6ef6cd9bdd95039`

Identical across all runs: **True**

