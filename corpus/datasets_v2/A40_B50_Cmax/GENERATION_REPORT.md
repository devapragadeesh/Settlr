# GENERATION REPORT -- A40_B50_Cmax

the one A x B interaction cell: the branch that produced all 50 wrong rows needs coverage < 100%, and D1 needs a big pool. v2: one batch's settlement_id names rows that are not its true composition, and the arithmetic still closes.

| axis | target | achieved |
|---|---|---|
| A pool size | 40 | mean 34.92, sizes [6, 40, 32, 44, 40, 37, 36, 40, 43, 30, 31, 40] |
| B attestation coverage | 1/2 | 6/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260918`, committed before generation.

## Volume

- recon rows: 599  {'payment': 509, 'refund': 60, 'adjustment': 30}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 484; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 4, 'not_unique': 7, 'unknown': 1}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 5, 'unknown_enumeration_capped': 7}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 0
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 7, 1: 2, 2: 3}
- reference gaps: min 4, max 37 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- none

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
