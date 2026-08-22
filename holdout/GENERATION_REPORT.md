# holdout/GENERATION_REPORT.md

Written by `holdout/generate_holdout.py` from the run that produced
`holdout/data/`. Every figure is derived from the emitted artefacts.

- seed: **20260905** (committed in `holdout/SEED.txt` **before** generation -- see `git log`)
- ledger period: **2026-09-14 .. 2026-11-27** (non-overlapping with the primary set)
- cut-offs: 2026-09-16 .. 2026-12-02, 12 weekly
- generator: `engine/generator.py`, **unmodified**, driven as a library

| quantity | value |
|---|---:|
| ledger rows | 240 |
| settlement batches (incl. re-settlements) | 15 |
| bank statement lines | 18 |
| of which DEBIT (reversal) lines | 3 |
| ERP orders | 184 |
| GSTR-2B lines | 21 |
| planted settlement reversals | 3 |

## Class coverage

The same 15 classes as the primary set, plus `h01`, which the primary
set does not contain and the engine has never encountered.

| class | count |
|---|---:|
| `c01_clean_1to1` | 152 |
| `c02_full_refund_pre_settlement` | 12 |
| `c03_partial_refund_pre_settlement` | 14 |
| `c04_refund_in_later_batch` | 13 |
| `c05_subset_sum_rolled_forward` | 21 |
| `c06_netting` | 13 |
| `c07_ambiguous_decomposition` | 3 |
| `c08_dispute_hold` | 6 |
| `c09_lost_dispute_adjustment` | 4 |
| `c10_won_dispute_settles_later` | 2 |
| `c11_cross_month_boundary` | 29 |
| `c12_shared_sid_null_utr` | 17 |
| `c13_schema_variance` | 57 |
| `c14_corrupt_bank_narration` | 4 |
| `c15_same_day_same_amount_decoy` | 8 |
| `h01_settlement_reversal_resettled` | 53 |

Classes absent: **none**

## Provenance -- `source_tier` distribution

| tier | rows |
|---|---:|
| `captured_real` | 14 |
| `synthesized_documented` | 84 |
| `synthesized_modelled` | 142 |

`h01` rows carry the tier of their underlying ledger row. The
REVERSAL MECHANISM itself is `synthesized_modelled`: Razorpay
documents no reversal behaviour, and `SETTLEMENT_SPEC.md` sec 10
says so. See `holdout/HOLDOUT_SPEC.md` sec 2.

## The planted reversals

| original UTR | credited | returned | re-settled under | rows | payout |
|---|---|---|---|---:|---:|
| `1791372600osmYw6` | 2026-10-07 | 2026-10-09 | `17919774000n3xCG` | 7 | 23060.17 |
| `1792582200GqaPVy` | 2026-10-21 | 2026-10-23 | `1793187000FQuOA5` | 22 | 82534.96 |
| `1794396600LGOvuF` | 2026-11-11 | 2026-11-13 | `17950014003XVRBM` | 21 | 84626.01 |

The ground-truth key records the linkage under `planted_reversals`,
with `reversed_by` on the original batch and `resettlement_of` on
the new one, so the relationship is recoverable in both directions.

