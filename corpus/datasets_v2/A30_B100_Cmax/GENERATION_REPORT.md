# GENERATION REPORT -- A30_B100_Cmax

the measured regime boundary: closure uniqueness collapses above ~30. v2: one batch's settlement_id names rows that are not its true composition, and the arithmetic still closes.

| axis | target | achieved |
|---|---|---|
| A pool size | 30 | mean 27.5, sizes [1, 35, 26, 40, 23, 31, 28, 23, 26, 37, 27, 33] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260912`, committed before generation.

## Volume

- recon rows: 455  {'payment': 389, 'refund': 45, 'adjustment': 21}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 369; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 9, 'not_unique': 3}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 9, 'unknown_enumeration_capped': 3}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 7
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 5, 1: 5, 2: 2}
- reference gaps: min 2, max 40 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
