# GENERATION REPORT -- A40_B50_Cmax

the one A x B interaction cell: the branch that produced all 50 wrong rows needs coverage < 100%, and D1 needs a big pool.

| axis | target | achieved |
|---|---|---|
| A pool size | 40 | mean 35.5, sizes [9, 42, 43, 46, 31, 28, 42, 38, 38, 34, 37, 38] |
| B attestation coverage | 1/2 | 6/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260901`, committed before generation.

## Volume

- recon rows: 599  {'payment': 509, 'refund': 60, 'adjustment': 30}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 483; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 2, 'unknown': 4, 'not_unique': 6}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 4, 'yes': 1, 'unknown_enumeration_capped': 7}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 0
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 6, 1: 5, 2: 1}
- reference gaps: min 1, max 40 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- none

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
