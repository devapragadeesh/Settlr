# GENERATION REPORT -- A20_Bnone_Cmax

the PSP artefact is ABSENT, not wrong. No settlement fields on the recon rows and no settlement report at all. The naive GROUP BY cannot run here; reconstruction is the only path.

| axis | target | achieved |
|---|---|---|
| A pool size | 20 | mean 19.0, sizes [3, 22, 14, 33, 15, 20, 18, 21, 18, 15, 26, 23] |
| B attestation coverage | 0 | 0/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260907`, committed before generation.

## Volume

- recon rows: 314  {'payment': 269, 'refund': 30, 'adjustment': 15}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 255; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 11, 'not_unique': 1}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 12}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 0
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 6, 1: 4, 2: 2}
- reference gaps: min 2, max 38 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d03_wrong_attestation` -- the PSP artefact is absent at this axis point, so there is no attestation to corrupt
- `d11_false_settlement_id` -- not planted at this axis point -- the original fourteen datasets are not regenerated, and this class ships only in corpus/datasets_v2/

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
