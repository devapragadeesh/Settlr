# GENERATION REPORT -- A40_B100_Cfifo



| axis | target | achieved |
|---|---|---|
| A pool size | 40 | mean 35.33, sizes [6, 37, 38, 38, 42, 32, 34, 37, 45, 36, 36, 43] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | fifo_under_cap | fifo_under_cap (phi=9/10) |

seed `20260904`, committed before generation.

## Volume

- recon rows: 599  {'payment': 509, 'refund': 60, 'adjustment': 30}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 483; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 7, 'not_unique': 5}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 9, 'unknown_enumeration_capped': 2, 'yes': 1}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 6
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 7, 1: 3, 2: 2}
- reference gaps: min 3, max 34 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
