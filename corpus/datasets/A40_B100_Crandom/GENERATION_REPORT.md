# GENERATION REPORT -- A40_B100_Crandom

the important cell: no objective can help, at a pool size where closure is measurably non-unique.

| axis | target | achieved |
|---|---|---|
| A pool size | 40 | mean 35.0, sizes [9, 33, 37, 33, 30, 29, 49, 45, 40, 42, 36, 37] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | random_valid | random_valid (phi=9/10) |

seed `20260905`, committed before generation.

## Volume

- recon rows: 599  {'payment': 509, 'refund': 60, 'adjustment': 30}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 483; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 8, 'not_unique': 4}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 8, 'unknown_enumeration_capped': 4}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 7
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 8, 1: 3, 2: 1}
- reference gaps: min 2, max 39 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
