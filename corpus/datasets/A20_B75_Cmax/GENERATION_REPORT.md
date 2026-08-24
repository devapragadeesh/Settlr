# GENERATION REPORT -- A20_B75_Cmax



| axis | target | achieved |
|---|---|---|
| A pool size | 20 | mean 18.58, sizes [2, 27, 21, 20, 21, 18, 22, 13, 20, 18, 21, 20] |
| B attestation coverage | 3/4 | 9/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260829`, committed before generation.

## Volume

- recon rows: 314  {'payment': 269, 'adjustment': 15, 'refund': 30}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 256; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 12}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 12}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 8
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 5, 1: 3, 2: 1, 5: 3}
- reference gaps: min 2, max 37 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- none

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
