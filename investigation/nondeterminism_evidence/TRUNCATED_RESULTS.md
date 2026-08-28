# Results — the `truncated` fix, against the committed prediction

Step 2.4. The prediction (`TRUNCATED_PREDICTION.md`) is checked here against a single
uncontended run of `corpus/baseline_old_engine.py --all` with the fix applied, compared
against the stable, pre-fix baseline (`corpus/baseline_results.json` as it stood after
Step 1 — the determinism fix, but before this one).

## Misses first

**Both predicted claims miss, and the miss is larger than predicted on both.**

1. **"0 to 5 enumerations flip."** Wrong, by a wide margin. `unrepresentable_claims`
   dropped in **16 of 30 datasets**, by **26** in total — and that number is a *lower
   bound* on the true flip count, not the count itself: it only captures flips that
   happened to touch an `Ambiguous` resolution whose `certain_rows` was non-empty before
   the fix (the D3 pattern `baseline_old_engine.py` tracks). A flip on an `Unresolved`
   outcome, or an `Ambiguous` resolution whose `certain_rows` was already empty for
   unrelated reasons, produces no visible change in this count at all. The true number of
   flipped enumerations is unknown and materially larger than the predicted 0–5.

2. **"No dataset's `Determinate` count decreases."** Wrong. **Three did:**

   | dataset | `Determinate` before | after |
   |---|---:|---:|
   | `datasets_v2/A20_B100_Cfifo` | 4 | 3 |
   | `datasets_v2/A40_B100_Cfifo` | 3 | 2 |
   | `datasets_v2/A40_B100_Cmax` | 3 | 2 |

   This is the headline, not a footnote, per the task's own instruction. **Three bank
   lines in the previously-published frozen-cascade results were reported `Determinate`
   — a claim of proven uniqueness — when the search that produced them had in fact been
   cut off by the deterministic-time budget before it could rule out a second
   decomposition.** They are `Unresolved` now, which is the honest, weaker statement: the
   search did not finish, so uniqueness was never established.

## Why the reasoning in the prediction was wrong, stated plainly

The prediction anchored on `ENUMERATION_CAP = 32` and the corpus's observed *candidate
counts*, reasoning that pools not hitting the cap would finish comfortably inside 30.0
deterministic-time units. That reasoning conflated two different costs: **finding**
solutions and **proving there are no more**. CP-SAT can find every actual solution to a
subset-sum instance quickly and still spend a large amount of deterministic time
exhausting the remaining branches to confirm completeness — that proof cost scales with
the structure of the search space (pools up to roughly 60 rows here), not with how many
solutions exist. A pool with exactly one solution can be *more* expensive to prove
complete over than a pool with ten, because the number of branches that must be visited
and ruled out is a property of the pool's size and value distribution, not of the answer.
The prediction treated "few solutions found" as evidence of "little search needed," and
that inference does not hold for exhaustive enumeration.

## Datasets with no observable change

**14 of 30** datasets show no change on any field checked (`outcomes`,
`unrepresentable_claims`, `mean_candidate_set_size`, `determined_abstained`,
`reconstructible_abstained`). Their enumerations either always resolved with
`status == OPTIMAL` (genuinely exhaustive) or hit the cap in a way that was already
reported correctly (`hit_cap` alone was sufficient there, since cap-hit was already
`truncated=True` before this fix).

## What replaces what

`corpus/baseline_results.json` is replaced again, with this run. The version it replaces
(stable under the determinism fix, but carrying the pre-Step-2 `truncated` bug) is kept at
`corpus/baseline_results_pretruncationfix.json` rather than discarded — a second
before/after pair, alongside `baseline_results_predeterminism.json` from Step 1.
