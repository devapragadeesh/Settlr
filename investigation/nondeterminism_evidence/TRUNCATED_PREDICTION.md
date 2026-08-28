# Prediction — the `truncated` fix, written before it exists

Step 2.1 of the follow-on task. `matching/stage3_solver.py`'s `enumerate_decompositions`
currently returns `truncated = hit_cap` (`len(collector.subsets) >= cap`) and separately
computes, but does not fold in, `over_time_budget = enum_status != cp_model.OPTIMAL and not
hit_cap`. An enumeration that exhausts its deterministic-time budget before reaching the cap
is therefore reported `truncated=False` — a stopped-early search recorded as a completed
one, `DECISIONS.md` §39's class for the third time in this codebase, one level deeper in the
same function the previous cycle just edited.

**Why this one is not merely cosmetic.** `matching/model.py:resolve_from_candidates` branches
on `truncated` directly: `len(unique) == 1 and not truncated` returns `Determinate` — a
confident claim of uniqueness. `len(unique) == 1 and truncated` returns `Unresolved`. A line
where the deterministic-time budget ran out after finding exactly one candidate, without
proving no second one exists, is currently indistinguishable from a line that was proven
unique — it is reported `Determinate` either way. This is the concrete failure mode the fix
closes, not an abstract completeness concern.

## No prior measurement exists to lean on

`corpus/baseline_old_engine.py`'s `measure()` records `mean_candidate_set_size` and the
outcome buckets per dataset, but nothing at the granularity of individual
`enumerate_decompositions` calls — `enum_status` and `over_time_budget` are computed inside
`matching/stage3_solver.py` and never surfaced to any artefact on disk. There is no committed
number to check this reasoning against before running it; the prediction below is reasoned
from the code and the shape of the corpus, not read off a prior run.

## The reasoning

`ENUMERATION_CAP = 32`. `THREE_SYSTEMS.md`'s per-dataset `mean k` column (mean candidate set
size, frozen-cascade column) already runs 15–30 on many cells, with means that high implying
individual bank lines regularly exceed 32 candidates outright — those lines hit the cap and
are `truncated=True` already, correctly, under both the old and new logic. The population
this fix can change is narrower: lines where the enumerator finds **fewer than 32** solutions
and **still** fails to reach `OPTIMAL` within 30.0 deterministic-time units — i.e., the search
space itself (not just the solution count) is large enough that proving *no more solutions
exist* costs more deterministic time than the budget allows, despite few solutions being
found. CP-SAT's cost for exhaustive enumeration scales with the structure of the constraint
(subset-sum over pools observed up to roughly 60 rows in this corpus), not with the solution
count alone, so this is a real but narrow category — most pools at this size that don't hit
the cap should exhaust well inside 30.0 deterministic-time units.

## The prediction

**A small number of enumerations flip `truncated` False → True — my best-guess range is 0 to
5 across all ~30 datasets × ~10–20 bank lines each — and I do not expect any dataset's
`Determinate` count to decrease as a result.** The second claim is stronger and more
falsifiable than the first: a `Determinate` decreasing requires the specific intersection of
(exactly one candidate found so far) AND (budget exhausted before the cap) AND (status not
already `OPTIMAL`), which is a narrow slice of an already-narrow slice.

**What would falsify this:** any flip count outside 0–5 is a miss on the first claim. **Any
decrease in any dataset's `Determinate` count is a miss on the second claim, and per the
task's own instruction, that is the headline of the report, not a footnote** — it would mean
the frozen cascade's published `Determinate` figures include at least one line that was never
actually proven unique.

**What I do not have a basis to predict:** which specific bank line, if any, is affected, or
which specific dataset. Nothing here is derived from running the code with the fix applied.
