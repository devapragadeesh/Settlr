# RESOLVER_SCALE_REPORT.md — throughput of the resolver

Produced by `eval/resolver_scale_report.py`. **Runtime only.** No accuracy claim is made on this data and none is computed — the same rule `scale/SCALE_REPORT.md` states for the frozen cascade, enforced by `tests/test_scale_degradation.py`.

This is `DECISIONS.md` §53's deferred measurement. §53 gave as its reason that the fixtures were format-incompatible and that measuring the resolver at scale would mean generating new corpus-format data. **That reason was factually wrong** — every `scale/data_*` already carries a schema-identical `recon_combined.json`, and the only divergence was two column names in `bank_statement.csv`. §72 fixed it in eleven lines. No new data was generated for this report.

## Read this before the table

**The resolver answers every line in tier B, at every size.** No `scale/data_*` ships a `settlement_report.csv`, so tier A is dead here; recon rows carry `settlement_id`, so tier B resolves every credit; and tier C — the reconstruction search — is **never reached**. What this report measures is the cost of `_verify`'s mandatory rival-count enumeration, one `closing_subsets` call per `Verified` over the full eligible pool. That cost is real. It is not the reconstruction search, and `12/12 Verified at 48,566 rows` is **not** evidence that the hard path scales. Measuring the hard path needs a fixture whose rows carry no `settlement_id` — a new dataset, not a flag.

## 1. The measurements

| rows | wall clock | rows/s | pool mean | pool max | worst solve | budget-bound | cap-bound | **COMPLETE** |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 246 | 67.43s | 4 | 28 | 40 | 12.13s | 6/12 | 0/12 | **6/12** |
| 505 | 66.90s | 8 | 58 | 83 | 12.45s | 4/12 | 6/12 | **2/12** |
| 997 | 90.19s | 11 | 114 | 163 | 16.86s | 2/12 | 9/12 | **1/12** |
| 2,452 | 155.99s | 16 | 285 | 383 | 27.47s | 2/12 | 9/12 | **1/12** |
| 4,876 | 147.27s | 33 | 562 | 768 | 37.20s | 2/12 | 10/12 | **0/12** |
| 9,732 | 211.42s | 46 | 1,146 | 1,527 | 42.81s | 0/12 | 12/12 | **0/12** |
| 24,298 | 349.23s | 70 | 2,842 | 3,799 | 77.69s | 0/12 | 12/12 | **0/12** |
| 48,566 | 510.63s | 95 | 5,678 | 7,526 | 100.64s | 4/12 | 8/12 | **0/12** |

12 bank lines and so 12 solves at every size; all lines are credits and all resolve `Verified`.

### The result is the last column, not the timings

**Above ~5,000 rows, not one enumeration completes.** Every solve stops early — on `max_deterministic_time` or on the solution cap — so every `rival_closure_count` the resolver reports at those sizes is a **lower bound**, and `rival_count_is_lower_bound` is set on all of them. The resolver still answers, and its answers are still warranted by tier B's attestation match; what degrades is its ability to say *how many rival compositions would have passed the same check*. That number is the whole of `Verified`'s honesty about its own strength, and past 5k rows it becomes 'at least N'.

The wall-clock curve is the less interesting half of this report. 510s for 48,566 rows is fine. Twelve lower-bounded rival counts is the finding.

### `incomplete_enumerations` reads 0 here and must not be believed

`ResolverOutput.accounting()` reports `incomplete_enumerations: 0` at every size above, including the rows where **no solve completed at all**. That is not a contradiction and not a bug: `resolver_contract/types.py` increments that counter only for `Ambiguous` outcomes (`incomplete += not outcome.candidate_set.complete`), and these fixtures produce zero `Ambiguous` — every line is `Verified` via tier B. The field is structurally 0 here regardless of what the solver did.

Nothing is hidden at the outcome level: each `Verified` carries its own `rival_count_is_lower_bound`. What is missing is an **aggregate** — the accounting has no counter for `Verified` whose rival count was truncated, so a reader of the summary sees `incomplete_enumerations: 0` and can reasonably conclude nothing truncated. On this family that inference is wrong at every size from 4,876 rows up.

**This report does not fix that.** Adding a counter to `Accounting` is a `resolver_contract` change, and this repository's rule is that a contract change is its own dated decision and never rides along with the work that provoked it. The numbers above are measured at the `closing_subsets` call site instead, which needs no contract change and is why this report can state the finding at all.

`pool mean`/`pool max` are the pools each solve **actually faced**, recorded by wrapping `closing_subsets` — not recomputed from `pool_at`, which without consumption is an upper bound that over-reports by ~4.5× at the small sizes. They are a different quantity from `scale/SCALE_REPORT.md`'s column, which is `matching/`'s per-batch pool. **The two must not be compared.**

## 2. The scaling curve

```
   246  ███████·············································     67.43s
   505  ███████·············································     66.90s
   997  █████████···········································     90.19s
  2452  ████████████████····································    155.99s
  4876  ███████████████·····································    147.27s
  9732  ██████████████████████······························    211.42s
 24298  ████████████████████████████████████················    349.23s
 48566  ████████████████████████████████████████████████████    510.63s
```

## 3. Why the total is bounded

Exactly **one CP-SAT solve per credit line**, each capped by `max_deterministic_time = 10.0` (`resolver/enumerate_closures.py`, §68) and by `DEFAULT_CAP` solutions. There is no accumulator across lines and no global deadline, so the ceiling is `credit_lines × per_solve` — which is why no point here runs away, in contrast to the frozen cascade whose per-solve wall budget bound each solve while the solve count itself grew.

**`max_deterministic_time` is not wall-clock, and the conversion is a function of pool size.** OR-Tools publishes no conversion, by design — §68 keeps the numeral 10.0 for exactly that reason. This is the first measurement of the ratio in this repository, taken on the slowest solve at each size:

| rows | worst-solve pool | wall | deterministic | seconds per unit |
|---:|---:|---:|---:|---:|
| 246 | 36 | 12.13s | 10.000 | **1.21** |
| 505 | 68 | 12.45s | 10.000 | **1.24** |
| 997 | 163 | 16.86s | 10.000 | **1.69** |
| 2,452 | 345 | 27.47s | 10.000 | **2.75** |
| 4,876 | 653 | 37.20s | 10.000 | **3.72** |
| 9,732 | 1,178 | 42.81s | 7.167 | **5.97** |
| 24,298 | 3,453 | 77.69s | 7.541 | **10.30** |
| 48,566 | 7,526 | 100.64s | 10.000 | **10.06** |

Anyone reading `DEFAULT_DETERMINISTIC_BUDGET = 10.0` as "about ten seconds" should read the last column first. The budget is a *search-effort* bound, not a time bound, and it buys steadily less wall-clock certainty as the pool grows — which is the property that makes it deterministic and the property that makes it hard to capacity-plan against. Both are true and §68 chose the first deliberately.

## 4. What this does not say

- **Nothing about accuracy.** Not measured, not computed, not claimed. `scale/truth_*` exists but uses the frozen generator's key schema, which `corpus/score_resolver.py` cannot read; scoring these fixtures needs an adapter and its own dated decision.
- **Nothing about the reconstruction search**, per the warning above.
- **Nothing about the frozen cascade.** `scale/SCALE_REPORT.md` is its artifact and is untouched by this script.

