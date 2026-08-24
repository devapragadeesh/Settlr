# GENERATION REPORT -- A20_B50_Cmax

where axis B does its real work. v2: one batch's settlement_id names rows that are not its true composition, and the arithmetic still closes.

| axis | target | achieved |
|---|---|---|
| A pool size | 20 | mean 18.83, sizes [4, 19, 23, 23, 18, 13, 23, 18, 23, 18, 27, 17] |
| B attestation coverage | 1/2 | 6/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260916`, committed before generation.

## Volume

- recon rows: 314  {'payment': 269, 'refund': 30, 'adjustment': 15}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 255; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 11, 'unknown': 1}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 11, 'unknown_enumeration_capped': 1}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 4
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 5, 1: 6, 2: 1}
- reference gaps: min 1, max 40 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- none

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
