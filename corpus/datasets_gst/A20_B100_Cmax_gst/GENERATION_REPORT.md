# GENERATION REPORT -- A20_B100_Cmax_gst

a real ITC-at-risk population over ~12 gateway 2B lines instead of the fixed 3-index plant: absent-from-2B, no-IRN and Rule-37A grounds drawn independently, so an invoice can carry more than one ground.

| axis | target | achieved |
|---|---|---|
| A pool size | 20 | mean 5.02, sizes [2, 4, 3, 3, 7, 7, 1, 2, 8, 6, 3, 12, 8, 6, 2, 4, 5, 4, 10, 6, 6, 3, 7, 8, 4, 6, 8, 3, 6, 5, 8, 3, 6, 7, 5, 5, 3, 4, 5, 3, 2, 2, 3, 5, 5, 6, 3, 5, 11, 3, 3] |
| B attestation coverage | 1 | 51/51 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20261001`, committed before generation.

## Volume

- recon rows: 314  {'payment': 269, 'refund': 30, 'adjustment': 15}
- settlements: 51
- bank lines: 59 (8 of them NOT ours)
- ERP invoices: 254; GSTR-2B lines: 59

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 50, 'not_unique': 1}
- true composition closes arithmetically: 51/51 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 51}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 50
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 19, 1: 16, 2: 9, 5: 7}
- reference gaps: min 1, max 40 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d03_wrong_attestation` -- no attested batch had >=3 credit rows to corrupt
- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure
- `d11_false_settlement_id` -- not planted at this axis point -- the original fourteen datasets are not regenerated, and this class ships only in corpus/datasets_v2/
- `d12_bank_side_mispost` -- not planted at this axis point -- wrong_bank_side is 0 here, and this class ships only in corpus/datasets_bankside/

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
