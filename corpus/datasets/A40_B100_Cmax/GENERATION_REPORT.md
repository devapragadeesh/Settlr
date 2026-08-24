# GENERATION REPORT -- A40_B100_Cmax



| axis | target | achieved |
|---|---|---|
| A pool size | 40 | mean 34.83, sizes [3, 43, 34, 43, 25, 41, 43, 37, 34, 40, 39, 36] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260827`, committed before generation.

## Volume

- recon rows: 599  {'payment': 509, 'adjustment': 30, 'refund': 60}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 484; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 5, 'unknown': 1, 'not_unique': 6}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 7, 'unknown_enumeration_capped': 4, 'yes': 1}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 5
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 7, 1: 1, 2: 3, 5: 1}
- reference gaps: min 4, max 35 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
