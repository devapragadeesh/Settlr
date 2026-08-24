# GENERATION REPORT -- A40_B100_Crandom

the important cell: no objective can help, at a pool size where closure is measurably non-unique. v2: one batch's settlement_id names rows that are not its true composition, and the arithmetic still closes.

| axis | target | achieved |
|---|---|---|
| A pool size | 40 | mean 40.09, sizes [35, 54, 36, 45, 35, 33, 43, 37, 40, 44, 39] |
| B attestation coverage | 1 | 11/11 |
| C selection rule | random_valid | random_valid (phi=9/10) |

seed `20260922`, committed before generation.

## Volume

- recon rows: 599  {'payment': 509, 'refund': 60, 'adjustment': 30}
- settlements: 11
- bank lines: 19 (8 of them NOT ours)
- ERP invoices: 482; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 4, 'not_unique': 7}
- true composition closes arithmetically: 11/11 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 7, 'unknown_enumeration_capped': 3, 'yes': 1}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 3
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 8, 1: 2, 2: 1}
- reference gaps: min 2, max 39 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
