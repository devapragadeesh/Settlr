# GENERATION REPORT -- A40_B100_Cmax_bankside

a larger pool where closure is measurably non-unique, so the mispost lands where a resolver also has more room to rationalize the wrong amount against SOME subset.

| axis | target | achieved |
|---|---|---|
| A pool size | 40 | mean 34.67, sizes [5, 26, 39, 43, 43, 29, 32, 40, 35, 43, 39, 42] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260925`, committed before generation.

## Volume

- recon rows: 599  {'payment': 509, 'refund': 60, 'adjustment': 30}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 484; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 8, 'not_unique': 4}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 11, 'unknown_enumeration_capped': 1}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 8
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 7, 1: 3, 2: 2}
- reference gaps: min 1, max 36 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d03_wrong_attestation` -- no attested batch had >=3 credit rows to corrupt
- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure
- `d11_false_settlement_id` -- not planted at this axis point -- the original fourteen datasets are not regenerated, and this class ships only in corpus/datasets_v2/

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
