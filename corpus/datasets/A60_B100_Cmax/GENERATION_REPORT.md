# GENERATION REPORT -- A60_B100_Cmax

above max_pool, so the simulator degrades to FIFO and says so. Closure is capped and the register says THAT too.

| axis | target | achieved |
|---|---|---|
| A pool size | 60 | mean 51.83, sizes [5, 43, 63, 43, 55, 46, 50, 62, 66, 49, 80, 60] |
| B attestation coverage | 1 | 12/12 |
| C selection rule | max_under_cap | max_under_cap (phi=9/10) |

seed `20260828`, committed before generation.

## Volume

- recon rows: 884  {'payment': 749, 'refund': 90, 'adjustment': 45}
- settlements: 12
- bank lines: 20 (8 of them NOT ours)
- ERP invoices: 711; GSTR-2B lines: 23

## Closure, measured with NO objective

The frozen key records subsets tying at the MAXIMUM. This records
every subset that closes, under no objective at all -- which is what
makes D1 measurable rather than latent.

- {'unique': 3, 'unknown': 1, 'not_unique': 8}
- true composition closes arithmetically: 12/12 (asserted at generation, not merely reported)
- truth present in the closure register: {'True': 4, 'unknown_enumeration_capped': 8}
- **determined instances** (unique closure, complete enumeration, attested, attestation correct): 3
  These are the lines on which `Unresolved` is a DEFECT, gated at
  zero by the resolver contract sec 6.1. Without them every guarantee
  in the contract is satisfiable by answering nothing.

## Bank independence

- posting lag histogram (days): {0: 6, 1: 4, 2: 2}
- reference gaps: min 9, max 40 (a dense sequence would be a counter minted for this file)

## Classes recorded as NOT planted

- `d04_unattested_settlements` -- attestation coverage is 100% at this axis point, so there is nothing unattested -- absent by design, not by failure

A class that could not be achieved by SELECTING organic rows is
recorded here as `planted: false` with its reason. No row is ever
minted to force a target -- that is defect D5, and it leaked in the
`amount` column before anyone read a description string.
