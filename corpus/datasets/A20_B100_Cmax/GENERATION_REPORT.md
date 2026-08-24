# GENERATION REPORT -- A20_B100_Cmax

spine. Closest to the frozen primary set: small pool, full attestation, the documented reading (B). Any sound resolver must score near-perfectly here.

| axis | target | achieved |
|---|---|---|
| A pool size | 20 | mean 19.0, sizes [4, 20, 23, 19, 16, 17, 20, 18, 22, 14, 27, 28] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260824`, committed before generation.

## Volume

- recon rows: 314  {'payment': 269, 'refund': 30, 'adjustment': 15}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 255; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 11, 'not_unique': 1}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 12}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 10
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 9, 1: 2, 5: 1}
- reference gaps: min 3, max 40 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
