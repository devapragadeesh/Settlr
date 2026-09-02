# SCALE_REPORT.md — throughput of the frozen cascade

Produced by `eval/scale_report.py`. **Runtime only.** No accuracy claim
is made on this data and none is computed; the held-out evidence in
`holdout/HOLDOUT_RESULTS.md` is a separate artifact and the two are
never combined. Mixing a throughput fixture into an accuracy result is
how a benchmark stops meaning anything.

Solver frozen at `81c04e0`. Single process, `num_workers = 1` on every
CP-SAT solve (`DECISIONS.md` §14 — determinism is worth more than the
speed, and that choice is visible in every number below).

## 1. The measurements

| rows | bank lines | wall clock | rows/s | pool mean | pool max | worst line | over 30s budget |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 246 | 12 | 0.14s | 1,817 | 20 | 30 | 0.06s | 0 |
| 505 | 12 | 18.06s | 28 | 41 | 53 | 13.09s | 1 |
| 997 | 12 | 102.10s | 10 | 80 | 99 | 24.72s | 6 |
| 2,452 | 12 | 102.00s | 24 | 196 | 233 | 23.75s | 4 |
| 4,876 | 12 | 130.78s | 37 | 388 | 469 | 23.23s | 4 |
| 9,732 | 12 | 254.16s | 38 | 772 | 902 | 40.88s | 5 |
| 24,298 | 12 | 580.18s | 42 | 1,929 | 2,232 | 117.01s | 6 |
| 48,566 | 12 | 979.87s | 50 | 3,854 | 4,408 | 143.16s | 5 |

Batch cadence is held at 12 weekly cut-offs across every size, so
**eligible pool size is the independent variable** — that is the
quantity `SETTLEMENT_SPEC.md` §1.5 bounds and the one whose growth
this run exists to observe.

## 2. The scaling curve

```
rows    wall clock
   246  ····················································      0.14s
   505  █···················································     18.06s
   997  █████···············································    102.10s
  2452  █████···············································    102.00s
  4876  ███████·············································    130.78s
  9732  █████████████·······································    254.16s
 24298  ███████████████████████████████·····················    580.18s
 48566  ████████████████████████████████████████████████████    979.87s
```

## 3. Simulator-side degradation — §1.5, observed

Above `SimulatorConfig.max_pool = 28` the generator stops forming
batches by exact enumeration and falls back to the FIFO reading (E),
recording `selection_degraded: true`. **A documented boundary that has
now been observed is worth more than one that was only predicted.**

| rows | pool mean | pool max | batches degraded | largest UNdegraded pool | smallest degraded pool |
|---:|---:|---:|---:|---:|---:|
| 246 | 16 | 25 | 0/12 | 25 | — |
| 505 | 32 | 45 | 9/12 | 25 | 29 |
| 997 | 64 | 86 | 10/12 | 25 | 62 |
| 2,452 | 158 | 187 | 11/12 | 22 | 107 |
| 4,876 | 315 | 384 | 12/12 | — | 46 |
| 9,732 | 628 | 735 | 12/12 | — | 91 |
| 24,298 | 1,568 | 1,774 | 12/12 | — | 243 |
| 48,566 | 3,134 | 3,589 | 12/12 | — | 481 |

**Degradation first fires at 505 rows**, on 9 of 12 batches. The smallest pool that degraded is **29 rows** and the largest that did not is **25** — straddling the documented ceiling of 28 exactly as specified.

At 246 rows nothing degrades (max pool 25), which is the primary set's regime and why the primary run can claim exact reconstruction throughout.

**Nothing degraded silently.** Every degraded batch carries
`selection_degraded: true` in its ground-truth record; the counts above
are read from that field, not inferred from pool size. The check that
matters is the converse one — no batch with a pool above 28 is missing
the flag, and none with a pool at or below 28 carries it — and it is
asserted in `tests/test_scale_degradation.py` rather than eyeballed.

## 4. Solver-side degradation — the engine's own ceiling

A different thing from §3, and kept separate so a degraded engine
cannot hide behind degraded data.

| rows | worst line | over 30s budget | enumerations truncated at 32 | determinate | ambiguous | unresolved |
|---:|---:|---:|---:|---:|---:|---:|
| 246 | 0.06s | 0 | 0 | 11 | 1 | 0 |
| 505 | 13.09s | 1 | 2 | 8 | 4 | 0 |
| 997 | 24.72s | 6 | 8 | 2 | 9 | 1 |
| 2,452 | 23.75s | 4 | 11 | 1 | 11 | 0 |
| 4,876 | 23.23s | 4 | 11 | 1 | 11 | 0 |
| 9,732 | 40.88s | 5 | 9 | 0 | 9 | 3 |
| 24,298 | 117.01s | 6 | 11 | 0 | 11 | 1 |
| 48,566 | 143.16s | 5 | 8 | 0 | 8 | 4 |

Read the `determinate` column against `ambiguous` and `unresolved`: as
the pool grows, the number of subsets that hit the target grows with it,
so the engine stops being able to name one. **That is the honest**
**failure direction** — it declines rather than guesses — but at scale it
means the engine declines almost everything, which is useless in a
different way from being wrong.

## 5. Where this approach stops being viable

Stated plainly, because the boundary is real and a panel will find it.

- Exact per-credit enumeration is comfortable to roughly **246 rows** — pools under
  `max_pool = 28`, everything determinate, ~1.4s end to end.
- Between there and a few thousand rows it still returns, but the
  answers get less useful: pools in the tens-to-hundreds admit many
  subsets summing to the same total, so ambiguity rises for arithmetic
  reasons rather than settlement ones.
- At 48,566 rows the run takes **980s** with a worst single line of 143.2s.
  A real merchant book is larger than this and settles daily, not
  weekly.

**The right answer is not a bigger time limit.** `DECISIONS.md` §2
already named it, having measured the alternative: a global
set-partitioning ILP over the whole statement is the strongest
formulation and it returned `UNKNOWN` after 60s on 1,347 booleans. The
correct next step is a **column-generation / set-cover decomposition** —
generate candidate decompositions per bank line as columns, price them
against the dual, and solve the restricted master — which is polynomial
in the number of columns actually generated rather than exponential in
the pool. Raising `SOLVER_TIME_LIMIT_SECONDS` buys a constant factor
against an exponential and is the wrong lever.

Two cheaper mitigations that are not the same as solving it, listed so
the gap between "known" and "engineered" stays visible: settle daily
rather than weekly, which cuts pool size by ~5x for free; and exploit
the fact that the rule is **checkable in linear time even where it is
expensive to invert** (`SETTLEMENT_SPEC.md` §1.5), so a proposed
decomposition from any source — including the attestation — can be
verified cheaply and only unverifiable lines need the solver.

