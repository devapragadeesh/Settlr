# RESOLVER_SCALE_REPORT.md — throughput of the resolver

Produced by `eval/resolver_scale_report.py`. **Runtime only.** No accuracy claim is made on this data and none is computed — the same rule `scale/SCALE_REPORT.md` states for the frozen cascade, enforced by `tests/test_scale_degradation.py`.

This is `DECISIONS.md` §53's deferred measurement. §53 gave as its reason that the fixtures were format-incompatible and that measuring the resolver at scale would mean generating new corpus-format data. **That reason was factually wrong** — every `scale/data_*` already carries a schema-identical `recon_combined.json`, and the only divergence was two column names in `bank_statement.csv`. §72 fixed it in eleven lines. No new data was generated for this report.

## Read this before the table

**The resolver answers every line in tier B, at every size.** No `scale/data_*` ships a `settlement_report.csv`, so tier A is dead here; recon rows carry `settlement_id`, so tier B resolves every credit; and tier C — the reconstruction search — is **never reached**. What this report measures is the cost of `_verify`'s mandatory rival-count enumeration, one `closing_subsets` call per `Verified` over the full eligible pool. That cost is real. It is not the reconstruction search, and `12/12 Verified at 48,566 rows` is **not** evidence that the hard path scales. Measuring the hard path needs a fixture whose rows carry no `settlement_id` — a new dataset, not a flag.

## 1. The measurements

| rows | bank lines | wall clock | rows/s | solves | pool mean | pool max | worst solve | budget-bound | Verified |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 246 | 12 | 67.43s | 4 | 12 | 28 | 40 | 12.13s | 6/12 | 12 |

`pool mean`/`pool max` are the pools each CP-SAT solve **actually faced**, recorded by wrapping `closing_subsets` at the call site — not recomputed from `pool_at`, which without consumption is an upper bound that over-reports badly at the top sizes. They are a different quantity from `scale/SCALE_REPORT.md`'s column, which is `matching/`'s per-batch pool. **The two must not be compared.**

`budget-bound` counts solves that stopped on `max_deterministic_time` rather than finishing or hitting the solution cap — i.e. where `rival_closure_count` is a lower bound and `rival_count_is_lower_bound` is set.

## 2. The scaling curve

```
   246  ████████████████████████████████████████████████████     67.43s
```

## 3. Why the total is bounded

Exactly **one CP-SAT solve per credit line**, each capped by `max_deterministic_time = 10.0` (`resolver/enumerate_closures.py`, §68) and by `DEFAULT_CAP` solutions. There is no accumulator across lines and no global deadline, so the ceiling is `credit_lines × per_solve` — which is why no point here runs away, in contrast to the frozen cascade whose per-solve wall budget bound each solve while the solve count itself grew.

**`max_deterministic_time` is not wall-clock, and the conversion is a function of pool size.** OR-Tools publishes no conversion, by design — §68 keeps the numeral 10.0 for exactly that reason. This is the first measurement of the ratio in this repository, taken on the slowest solve at each size:

| rows | worst-solve pool | wall | deterministic | seconds per unit |
|---:|---:|---:|---:|---:|
| 246 | 36 | 12.13s | 10.000 | **1.21** |

Anyone reading `DEFAULT_DETERMINISTIC_BUDGET = 10.0` as "about ten seconds" should read the last column first. The budget is a *search-effort* bound, not a time bound, and it buys steadily less wall-clock certainty as the pool grows — which is the property that makes it deterministic and the property that makes it hard to capacity-plan against. Both are true and §68 chose the first deliberately.

## 4. What this does not say

- **Nothing about accuracy.** Not measured, not computed, not claimed. `scale/truth_*` exists but uses the frozen generator's key schema, which `corpus/score_resolver.py` cannot read; scoring these fixtures needs an adapter and its own dated decision.
- **Nothing about the reconstruction search**, per the warning above.
- **Nothing about the frozen cascade.** `scale/SCALE_REPORT.md` is its artifact and is untouched by this script.

