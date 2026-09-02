# GENERATION REPORT -- A20_B100_Cmax_gst_noisy

identical population, plus a 4x larger vendor-noise pool: isolates whether identify_supplier() still finds the true gateway GSTIN as the haystack grows, separately from the population question the plain _gst point asks.

| axis | target | achieved |
|---|---|---|
| A pool size | 20 | mean 5.06, sizes [6, 7, 4, 2, 5, 3, 2, 4, 3, 5, 3, 4, 11, 5, 7, 10, 2, 7, 9, 8, 8, 8, 5, 2, 5, 3, 4, 2, 7, 4, 3, 6, 2, 5, 4, 3, 6, 4, 5, 2, 4, 10, 6, 7, 6, 9, 2, 11, 2, 4, 2] |
| B attestation coverage | 1 | 51/51 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20261003`, committed before generation.

## Volume

- recon rows: 314  {'payment': 269, 'adjustment': 15, 'refund': 30}
- settlements: 51
- bank lines: 59 (8 of them NOT ours)
- ERP invoices: 254; GSTR-2B lines: 167

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

- posting lag histogram (days): {0: 25, 1: 15, 2: 8, 5: 3}
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
