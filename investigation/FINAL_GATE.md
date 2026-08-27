# FINAL GATE — stopped early: a genuine defect surfaced in Step 3.4

**Status: STOPPED per this task's own constraint** — *"If Step 3 finds a
genuine soundness defect — anything that would move a zero-gate — STOP AND
REPORT. Do not fix it inline."* Steps 3.3–3.6 have not been completed. This
document reports what was found and why work paused rather than continuing.

Nothing in `matching/`, `resolver/`, `resolver_contract/`, `corpus/oracle.py`
or any dataset has been modified. The defect below is **in frozen code** and
this task is not authorized to touch it.

---

## 0. Lead: the frozen baseline (`matching/`) is not deterministic

Steps 1 and 2 are complete and clean (below). Step 3.3 began with a clean
clone, and while setting it up a background re-run of
`corpus/baseline_old_engine.py --all` — started earlier for an unrelated
reason — finished and was compared against the version already committed at
`corpus/baseline_results.json`. **They disagree, and not only on wall-clock
timing.**

Two runs of the same frozen `matching/` cascade (commit `81c04e0`, per
`corpus/BASELINE_OLD_ENGINE.md`) against the same frozen dataset files produce
**different outcome distributions**:

| dataset | run A `outcomes` | run B `outcomes` |
|---|---|---|
| `A30_B100_Cmax` | `Determinate:4, Ambiguous:6, Unresolved:10` | `Determinate:4, Ambiguous:7, Unresolved:9` |
| `A40_B100_Cfifo` | `Determinate:4, Ambiguous:7, Unresolved:9` | `Determinate:5, Ambiguous:7, Unresolved:8` |
| `A60_B100_Cmax` | `Determinate:1, Unresolved:12, Ambiguous:7` | `Determinate:1, Unresolved:11, Ambiguous:8` |
| `datasets_v2/A20_B0_Cmax` | `Determinate:4, Unresolved:7, Ambiguous:9` | `Determinate:4, Unresolved:8, Ambiguous:8` |
| `datasets_v2/A40_B100_Cmax` | `Determinate:2, Unresolved:9, Ambiguous:9` | `Determinate:2, Unresolved:8, Ambiguous:10` |
| `datasets_v2/A60_B100_Cmax` | `Ambiguous:13, Unresolved:6, Determinate:1` | `Ambiguous:14, Unresolved:5, Determinate:1` |

`mean_candidate_set_size`, `unrepresentable_claims`, `determined_abstained`,
and the specific bank lines carrying a `certain_rows`-based unrepresentable
claim all move with it. **8 of 30 datasets disagree between the two runs.**
This is not floating-point noise in a reported average; a line that was
`Determinate` in one run is `Ambiguous` in another, on identical frozen input.

## 1. The mechanism, confirmed against the frozen code

`matching/stage3_solver.py:67`:

```python
SOLVER_TIME_LIMIT_SECONDS = 30.0
```

used at lines 177 and 203:

```python
solver.parameters.num_workers = 1          # determinism
solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
...
enumerator.parameters.num_workers = 1      # determinism
enumerator.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
```

`num_workers = 1` is commented `# determinism` and does make CP-SAT's search
*order* reproducible under a given clock. It says nothing about *how much
search happens before the clock cuts it off* — and `max_time_in_seconds` is
measured against the **wall clock**, not CP-SAT's internal step count. Run A
and run B differ in what else was running on the machine at the time (this
session had a concurrent oracle run active during at least one of them), so
identical search orders were cut off at different points, producing different
enumerated subset sets and therefore different `Determinate`/`Ambiguous`
classifications downstream.

**This is `DECISIONS.md` §39's exact defect — a truncated search recorded
through the same code path as a completed one, because completeness was never
checked against the solver's own status, only inferred from an external
clock** — except found here in the code the resolver was built to replace, not
in the resolver.

## 2. Why this matters more here than it did in §39

§39's version lived in `resolver/enumerate_closures.py`, was caught before
shipping, and never affected a published number because it was fixed pre-oracle.
This instance is in `matching/`, which is:

* **frozen**, per this repository's own rules, at commit `81c04e0`;
* the source of **every frozen-cascade figure quoted anywhere in this
  repository** — `corpus/THREE_SYSTEMS.md`'s "frozen cascade" column,
  `SCORECARD.md`, `README.md`'s three-system comparison, and the original
  50-wrong-answers finding that motivated this entire project
  (`CHECKPOINT.md` §0, `DECISIONS.md` §1);
* **already committed to `corpus/baseline_results.json`** and rendered into
  `corpus/BASELINE_OLD_ENGINE.md`, which is itself governed by its own
  predict-then-freeze protocol (`git log`: `0000ad0` → `5460752` → `3f26983`)
  that assumes a single run is authoritative.

If the frozen cascade's outcome on a given bank line depends on background CPU
load at the moment it happened to run, then **every frozen-cascade figure in
this repository carries an unstated confidence interval**, and the comparison
table's "frozen cascade: 55/56 right, 1 wrong" is one draw from a distribution,
not a fixed fact about frozen code.

## 3. What is NOT affected

* **No resolver number moves.** `resolver/enumerate_closures.py` fixed exactly
  this class in `DECISIONS.md` §39 by checking `status == OPTIMAL` rather than
  an external clock, and that fix is verified holding by
  `resolver/tests/test_pool_frame.py` and the oracle's zero gates (G1, G2, G4,
  G6, G9 — all zero, unaffected by this finding).
* **No oracle gate moves.** The oracle scores the resolver, not `matching/`.
* **The corpus, `resolver/`, `resolver_contract/` and `corpus/oracle.py` are
  unmodified** by this finding or by this task.

## 4. What was checked before concluding this is real, not an artefact of my measurement

* Confirmed both JSON files are complete (30 rows each) and both processes
  exited normally on their datasets — no truncated/partial write.
* Confirmed `num_workers = 1` is present in the code, ruling out
  non-determinism from parallel search order.
* Confirmed `max_time_in_seconds` is measured against wall time
  (`time.perf_counter()` brackets the call) rather than a CP-SAT-internal
  deterministic budget — `ortools` does expose deterministic time limits via
  `solver.parameters.max_deterministic_time`, which is **not** used here.
* This session ran a resolver oracle pass and this baseline re-run
  concurrently on the same machine, which is the load asymmetry that produces
  the divergence — consistent with the mechanism rather than a mystery.

## 5. Recommendation — not implemented, reported for a decision

This needs a **freeze-and-rescore cycle of its own**, out of scope for a
diagnostic task, and it touches frozen code:

1. Switch `max_time_in_seconds` to `max_deterministic_time` (CP-SAT's
   load-independent budget), the direct analogue of the resolver's own §39 fix,
   applied to the baseline instead.
2. Re-run `corpus/baseline_old_engine.py --all` **alone**, with no concurrent
   process, and confirm three consecutive runs are byte-identical (this is
   exactly Step 3.4, deferred).
3. If outcomes still move under the corrected budget, that is a second,
   independent finding — non-determinism in the search itself, not the clock —
   and would need its own investigation.
4. Every downstream figure quoted from `corpus/baseline_results.json` /
   `corpus/BASELINE_OLD_ENGINE.md` needs re-verification once a stable run
   exists, since the currently-committed run is one draw among at least two
   observed to disagree.

**This is a decision for the person running this project, not for this task to
make unilaterally**, because it means editing code inside the FROZEN
boundary — even though the edit is the same one-line class of fix already
validated in `resolver/`. Confirm before I touch `matching/stage3_solver.py`.

---

## What WAS completed before the stop

### Step 1 — coverage metric, fixed

`corpus/coverage.py` is the single implementation of the three-way split
(`answered` / `not_determinable` / `record_contradicted`), consumed by
`corpus/score_resolver.py`, `corpus/three_systems.py`, `corpus/scorecard.py`
and `corpus/claims_ledger.py`. Regenerated and confirmed:

| scope | answered | not determinable | record contradicted | coverage on determinable lines |
|---|---:|---:|---:|---:|
| all 30 datasets | 276 | 21 | 62 | 276/297 (92.9%) |
| the 28 datasets with a PSP artefact | 275 | **0** | 60 | **275/275 (100.0%)** |
| the 2 PSP-absence datasets | 1 | 21 | 2 | 1/22 (4.5%) |
| the original 14 | 143 | **0** | 25 | **143/143 (100.0%)** |

`DECISIONS.md` §48 records the defect, the measurement, the rejected
alternative (prose caveat — rejected, prose does not survive a skim), and
folds it into §44.4 as the **third** instance of this project committing the
error it had just catalogued.

Verified the resolver's own oracle gates did not move under the
`corpus/score_resolver.py` change: **G1 0, G2 0, G3 20, G4 0, G6 0, G7 0, G8
15, G9 0, 28/30 passing** — identical to the pre-fix run.

### Step 2 — truncation announcement, fixed, and a second instance found

`corpus/score_resolver.py`'s `violations` field now carries `violations_total`
and `violations_truncated`. `corpus/tests/test_truncation_is_announced.py`
adds a static guard: any dict value built from a slice must have a
`*_truncated` flag declared somewhere in the same function.

That guard immediately found a **second, previously unknown instance**:
`corpus/baseline_old_engine.py`'s `detail` block capped three lists at 8 rows
with no flag. Fixed the same way (`DETAIL_SAMPLE = 8`, `detail_truncated`,
`detail_total`).

Confirmed in both cases: `violations_by_gate` (the field every published gate
number derives from) and the `outcomes`/counts fields (in the baseline) were
always complete. **No published number was affected by either truncation.**

Watched to fail: the static guard was run against a copy of
`score_resolver.py` with the flag removed; it named the file, function and
line. Reverted.

### Step 3.1 — staleness sweep across all generated documents

Full sweep against `corpus/oracle_results.json` after the coverage fix. Found:

* Three hand-typed figures in `README.md` (`699`, `4,295`, `1,469`) stale
  since the F1 fix (current: 701, 4,308, 1,472). **Replaced with a generated
  block** (`corpus/three_systems.py:split_figures`), because this is the
  **fourth** time a hand-typed number in this repository has gone stale — see
  `DECISIONS.md` §44.4's three-instance list, now due a fourth entry.
* Two historical figures in `CHECKPOINT.md` (238/275 non-decisive; the
  82.1%/85% single-figure coverage) — these are legitimate as-of-the-time
  records and were annotated as superseded rather than edited, per this
  task's own rule that historical claims should be marked, not silently
  corrected.

### Step 3.2 — normative claims checked against code

13 checks against `resolver_contract/types.py`, `resolver/resolve.py`,
`resolver/breaks.py` and `corpus/oracle.py`: only-`Verified`-consumes,
`Ambiguous` has no `decomposition`, no `resolver/` module reads
`ground_truth.json`, `ProvenUnmatched` reasons never call `pool_at`,
`rival_closure_count` is a required field, `ProvenUnmatchedReason` has exactly
two members, `OpenBreak` carries no composition, G5 is not raised anywhere, no
LLM anywhere under `resolver/`, no float literals in money paths.

**13 of 13 hold.** (One false alarm in my own first pass — a naive text search
flagged three docstrings *describing* the ground-truth prohibition and the one
constant *enforcing* it; corrected to an AST check that excludes docstrings and
re-ran clean.)

### Step 3.3 — clean clone, partially complete

Fresh clone, fresh venv, `pip install -r requirements.txt`: clean. Frozen hash
verification: **all `engine/data/*` and `engine/ground_truth/*` files verify
OK**; **all 208 corpus dataset files across `datasets/` and `datasets_v2/`
verify OK**. One documentation gap found and fixed: `README.md` did not
document the corpus verification command or explain the (harmless) `sed`
formatting warning on the engine manifest; both are now documented.

**Not completed**: the documented `run_all.py` and `pytest` commands were not
yet re-run end-to-end from the clean clone, because the baseline
non-determinism surfaced first and changes what "the documented commands
succeed" should mean while it is unresolved.

### Steps 3.4, 3.5, 3.6 — not started

Determinism (3.4) is the check that surfaced this finding as a side effect;
running it properly, in isolation, is now item 2 of the recommendation above
rather than a completed step. The hostile-reader pass (3.5) and one-sentence
test (3.6) were not begun, since they would be auditing figures that may need
to change once the baseline is stabilized.

---

## Summary

| step | status |
|---|---|
| 1 — coverage metric | **done** |
| 2 — truncation announcement | **done**, plus one extra instance found and fixed |
| 3.1 — staleness sweep | **done** |
| 3.2 — normative claims vs code | **done**, 13/13 hold |
| 3.3 — clean clone | **partial** — deps and hashes verified; full command re-run deferred |
| 3.4 — determinism ×3 | **not run** — its purpose was overtaken by the finding above |
| 3.5 — hostile reader | **not started** |
| 3.6 — one-sentence test | **not started** |

**One thing found that was worse than expected, and it is the headline of this
document:** the frozen `matching/` cascade — the baseline every comparison in
this repository is measured against — is not deterministic under load, for the
same reason `DECISIONS.md` §39 named and fixed in the resolver. It was found
by accident, by the same kind of check this task's Step 3.4 asks for, applied
one component over from where it was aimed. Fixing it touches frozen code and
needs an explicit decision before it happens.
