# GENERATION REPORT -- A30_B100_Cmax

the measured regime boundary: closure uniqueness collapses above ~30.

| axis | target | achieved |
|---|---|---|
| A pool size | 30 | mean 28.58, sizes [4, 30, 38, 28, 27, 30, 33, 40, 23, 19, 34, 37] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260826`, committed before generation.

## Volume

- recon rows: 455  {'payment': 389, 'refund': 45, 'adjustment': 21}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 369; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 10, 'not_unique': 2}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 11, 'unknown_enumeration_capped': 1}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 9
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 6, 1: 5, 2: 1}
- reference gaps: min 2, max 40 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
