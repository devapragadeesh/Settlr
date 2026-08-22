# ROBUSTNESS.md

## Why this file exists

The dataset is a pure function of one integer. A git timestamp proves the
bytes existed at time T; it cannot prove nobody tried seeds until the
numbers looked good. **This table is the answer to that attack**: the same
generator, run over seeds `0..19` — a contiguous range, not a
selection — produces the same structure with the same classes present.

## What the shipped seed WAS selected for

Stating this plainly, because omitting it would be the dishonest version.
Seed `20260822` was picked from a sweep under exactly two constraints:

1. the dataset lands on **exactly 240 rows**;
2. **at least two** batches come out provably ambiguous.

Nothing else was selected for, and nothing else *could* have been: at the
time of selection no solver existed, so no accuracy, match-rate or
solvability property was observable. The table below is what shows that
those two constraints are ordinary draws rather than a lucky corner.

## Class counts across seeds

| class | min | median | max | seeds with zero |
|---|---:|---:|---:|---:|
| `c01_clean_1to1` | 134 | 149 | 154 | 0 |
| `c02_full_refund_pre_settlement` | 10 | 12 | 16 | 0 |
| `c03_partial_refund_pre_settlement` | 12 | 16 | 24 | 0 |
| `c04_refund_in_later_batch` | 10 | 15 | 24 | 0 |
| `c05_subset_sum_rolled_forward` | 9 | 19 | 46 | 0 |
| `c06_netting` | 9 | 11 | 12 | 0 |
| `c07_ambiguous_decomposition` | 0 | 2 | 5 | **2** |
| `c08_dispute_hold` | 4 | 5 | 7 | 0 |
| `c09_lost_dispute_adjustment` | 4 | 4 | 4 | 0 |
| `c10_won_dispute_settles_later` | 1 | 2 | 4 | 0 |
| `c11_cross_month_boundary` | 27 | 39 | 56 | 0 |
| `c12_shared_sid_null_utr` | 10 | 14 | 18 | 0 |
| `c13_schema_variance` | 40 | 53 | 66 | 0 |
| `c14_corrupt_bank_narration` | 3 | 3 | 3 | 0 |
| `c15_same_day_same_amount_decoy` | 8 | 8 | 8 | 0 |

## Shape

| quantity | min | median | max |
|---|---:|---:|---:|
| recon rows | 239 | 241 | 254 |
| batches | 10 | 12 | 12 |
| ambiguous batches | 0 | 2 | 5 |

## Reading this table

A class whose **seeds with zero** column is non-zero is a class the
generator cannot deliver on every seed. Those are named here rather than
hidden: the generator records every missed plant in the ground-truth key
as `planted: false` with a reason, instead of quietly shipping a smaller
dataset and letting the class count drift.

**Ambiguity is the one class that is not always reachable.** It requires a
sum below the live-balance cap that two distinct subsets of the eligible
pool both hit; on some ledgers no such sum exists. That is a property of
the rule, not a defect in the generator, and it is why the shipped seed
was constrained to produce at least two.

Row count varies by seed because planting inserts a variable number of
calibration debits.

