# GENERATION REPORT -- A20_B100_Cmax_bankside

spine pool size, full attestation, one bank-side mispost: the sources agree on the PSP side and disagree on the bank side -- the untested half of the AttestationDiscrepancy symmetry.

| axis | target | achieved |
|---|---|---|
| A pool size | 20 | mean 19.17, sizes [2, 22, 21, 25, 33, 17, 18, 14, 18, 15, 29, 16] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260924`, committed before generation.

## Volume

- recon rows: 314  {'payment': 269, 'refund': 30, 'adjustment': 15}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 256; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 11, 'not_unique': 1}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 12}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 11
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 3, 1: 7, 2: 2}
- reference gaps: min 2, max 40 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d03_wrong_attestation` -- no attested batch had >=3 credit rows to corrupt
- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure
- `d11_false_settlement_id` -- not planted at this axis point -- the original fourteen datasets are not regenerated, and this class ships only in corpus/datasets_v2/

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
