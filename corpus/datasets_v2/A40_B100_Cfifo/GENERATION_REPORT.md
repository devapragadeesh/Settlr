# GENERATION REPORT -- A40_B100_Cfifo

 v2: one batch's settlement_id names rows that are not its true composition, and the arithmetic still closes.

| axis | target | achieved |
|---|---|---|
| A pool size | 40 | mean 34.92, sizes [1, 40, 26, 38, 44, 27, 34, 44, 37, 48, 45, 35] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | fifo_under_cap | fifo_under_cap (phi=9/10) |

seed `20260921`, committed before generation.

## Volume

- recon rows: 599  {'payment': 509, 'refund': 60, 'adjustment': 30}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 484; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 7, 'not_unique': 5}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 8, 'unknown_enumeration_capped': 4}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 5
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 4, 1: 5, 2: 1, 5: 2}
- reference gaps: min 1, max 39 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
