# FINAL GATE — complete

This document was stopped once, mid-way, when Step 3.4 surfaced a genuine defect in frozen
code (§0 below, preserved). That defect and a second one found while fixing it are now
resolved, verified, and recorded in `DECISIONS.md` §49–§50. This is the completed document:
every step below states what was checked, what was found, what was fixed, and — for the
checks that came back clean — that the check was exhaustive and what its scope was. A clean
result is only evidence when both of those are stated.

---

## 0. The defect that stopped this document, and its resolution

Steps 1 and 2 (below) were done. Step 3.4 (determinism, ×3) began with a clean clone, and
while setting it up a background re-run of `corpus/baseline_old_engine.py --all` — started
earlier for an unrelated reason — finished and was compared against the version already
committed at `corpus/baseline_results.json`. **They disagreed**, and not only on wall-clock
timing: two runs of the same frozen `matching/` cascade (commit `81c04e0`) against the same
frozen dataset files produced different outcome distributions on 10 of 30 datasets.

**Mechanism:** `matching/stage3_solver.py` budgeted its CP-SAT solves with
`max_time_in_seconds` — a wall-clock limit — so identical, reproducible search orders
(`num_workers = 1`) were cut off at different points depending on machine load.
`DECISIONS.md` §39's exact defect class, found in the code the resolver was built to
replace rather than in the resolver.

**Resolution, in full, across two fix cycles (`DECISIONS.md` §49, §50):**

- §49: `max_time_in_seconds` → `max_deterministic_time`. Verified — not assumed —
  reproducible: three uncontended runs of `corpus/baseline_old_engine.py --all` are
  byte-identical excluding wall-clock `seconds`, and a fourth, deliberately contended run
  (`corpus/score_resolver.py --all` running concurrently, reproducing the exact condition
  that caused the original divergence) matches all three. A committed prediction (weak lean
  toward one of the two historical runs) was **not confirmed** — the stable result matches
  neither historical draw on 6 of the 10 originally-disagreeing datasets.
- §50: while fixing §49, a second, adjacent defect was found in the same function and
  deliberately deferred to its own cycle: `truncated` was computed from the enumeration cap
  alone, never from the solver's own status, so a search that exhausted its deterministic-time
  budget before reaching the cap was reported as if it had finished. Fixed in its own
  predict → fix → watched-to-fail-test → verify cycle. The committed prediction (0–5 flips,
  no `Determinate` decrease) **missed badly**: at least 26 enumerations flipped (a measured
  lower bound, not the true count), and **three previously-published `Determinate` results
  were never actually proven unique** — `datasets_v2/A20_B100_Cfifo` (4→3),
  `datasets_v2/A40_B100_Cfifo` (3→2), `datasets_v2/A40_B100_Cmax` (3→2).

`corpus/baseline_results.json` was replaced twice, once per fix; both prior draws are
preserved (`corpus/baseline_results_predeterminism.json`,
`corpus/baseline_results_pretruncationfix.json`) rather than discarded. Every downstream
figure sourced from it — `corpus/THREE_SYSTEMS.md`, `README.md`'s spliced summary,
`CHECKPOINT.md` §4.6 (twice, dated) — was recomputed, not eyeballed for closeness.
`CLAIMS.md` and `SCORECARD.md` were checked both times and confirmed unaffected. Full
accounting: `investigation/nondeterminism_evidence/`.

**No resolver number moved at any point.** `resolver/`'s own instance of this class was
already fixed at §39, and the oracle's soundness gates (G1, G2, G4, G6, G9) are all still
zero. This was entirely a frozen-cascade-only defect, in the code the comparison table
measures *against*, not in the thing being evaluated.

---

## 1. Coverage metric, fixed

`corpus/coverage.py` is the single implementation of the three-way split (`answered` /
`not_determinable` / `record_contradicted`), consumed by `corpus/score_resolver.py`,
`corpus/three_systems.py`, `corpus/scorecard.py` and `corpus/claims_ledger.py`. Regenerated
and confirmed:

| scope | answered | not determinable | record contradicted | coverage on determinable lines |
|---|---:|---:|---:|---:|
| all 30 datasets | 276 | 21 | 62 | 276/297 (92.9%) |
| the 28 datasets with a PSP artefact | 275 | **0** | 60 | **275/275 (100.0%)** |
| the 2 PSP-absence datasets | 1 | 21 | 2 | 1/22 (4.5%) |
| the original 14 | 143 | **0** | 25 | **143/143 (100.0%)** |

`DECISIONS.md` §48 records the defect, the measurement, the rejected alternative, and folds
it into §44.4 as the third instance of this project committing the error it had just
catalogued. Resolver oracle gates confirmed unmoved: G1 0, G2 0, G3 20, G4 0, G6 0, G7 0,
G8 15, G9 0, 28/30 passing.

## 2. Truncation announcement, fixed, and a second instance found

`corpus/score_resolver.py`'s `violations` field carries `violations_total` and
`violations_truncated`. `corpus/tests/test_truncation_is_announced.py` statically guards
that any dict value built from a slice declares a `*_truncated` flag in the same function.
That guard immediately found a second, previously-unknown instance:
`corpus/baseline_old_engine.py`'s `detail` block capped three lists at 8 rows with no flag.
Fixed the same way. In both cases `violations_by_gate` and the outcome/count fields — the
ones every published number derives from — were always complete; no published number was
affected by either truncation. Watched to fail: the guard was run against a copy with the
flag removed, named the file/function/line, reverted.

## 3.1 Staleness sweep across all generated documents

Full sweep against `corpus/oracle_results.json` after the coverage fix. Found and fixed
three hand-typed, stale figures in `README.md` (replaced with a generated block,
`corpus/three_systems.py:split_figures` — the fourth instance of a hand-typed number going
stale, `DECISIONS.md` §44.4). Two historical `CHECKPOINT.md` figures annotated as superseded
rather than silently edited, since they were legitimate as-of-the-time records.

## 3.2 Normative claims checked against code

13 checks against `resolver_contract/types.py`, `resolver/resolve.py`, `resolver/breaks.py`
and `corpus/oracle.py`: only-`Verified`-consumes, `Ambiguous` has no `decomposition`, no
`resolver/` module reads `ground_truth.json`, `ProvenUnmatched` reasons never call
`pool_at`, `rival_closure_count` is required, `ProvenUnmatchedReason` has exactly two
members, `OpenBreak` carries no composition, G5 is not raised anywhere, no LLM anywhere
under `resolver/`, no float literals in money paths. **13 of 13 hold.** (One false alarm in
the first pass — a naive text search flagged docstrings describing the prohibition, not
violating it; corrected to an AST check excluding docstrings, re-ran clean.)

## 3.3 Clean clone — completed

Run twice: once when this document first stopped (deps and hashes verified, full command
re-run deferred pending §0's resolution), and once now, completed end to end.

- **Fresh clone, fresh venv, `pip install -r requirements.txt`**: clean, both times.
- **Frozen hash verification**: all 6 `engine/data/*` and `engine/ground_truth/*` files
  verify OK (the one `shasum` formatting warning is the documented, expected one — the
  manifest's trailing blank line). All 30 corpus dataset `DATASET_HASHES.txt` manifests
  verify with **0 failures**.
- **`pytest tests engine/tests corpus/tests resolver/tests -q`, run verbatim**: found a real
  defect the first time — 16 failures in `tests/test_scale_degradation.py`. Root cause:
  `scale/MANIFEST.json` is committed, but the fixture data it points to
  (`scale/data_*/`, `scale/truth_*/`, gitignored, regenerated by `scale/generate_scale.py`)
  is not, so a fresh clone has the manifest without the data. The test file's skip guard
  checked only the manifest's existence. **Fixed**: the guard now checks the first fixture's
  actual `truth_dir`. Verified both directions — 20 real tests still pass where fixtures
  exist (this machine), 20 skip cleanly where they don't (the clone). Suite result after the
  fix, in the clone: **824 passed, 27 skipped** — which is exactly the main checkout's 844
  passed minus the 20 scale tests this clone cannot run for real, confirming the fix, not a
  coincidence.
- **`python3 run_all.py`, run verbatim, timed**: completed clean, exit 0 at every step.
  **63m42s** (baseline 2557s / 42.6min, resolver 1265s / 21.1min), slightly over the
  previously-documented "30-60 min." `README.md` and `run_all.py`'s own docstring corrected
  to state what was measured and to note that wall-clock duration is expected to vary with
  machine speed now that the frozen cascade's stopping point is measured in CP-SAT
  deterministic time, not wall-clock time — variable duration with a fixed outcome is the
  intended property of the §49 fix, not a regression.

**Scope of this check, stated exactly**: one fresh clone, one fresh venv, on this machine,
run once end to end after the fix. It is not a claim that the timing is stable across
machines or repeated runs — only that this run completed correctly and matched expectations
once the one real defect it found was fixed.

## 3.4 Determinism, ×3 — completed

This is the check whose *purpose* — verifying the frozen cascade is reproducible — is what
surfaced §0's defect as a side effect, before the check itself could run as originally
planned. Run properly afterward, twice (once per fix cycle): three consecutive uncontended
runs of `corpus/baseline_old_engine.py --all`, confirmed byte-identical excluding wall-clock
`seconds`, plus one deliberately contended run (concurrent `corpus/score_resolver.py --all`)
confirmed to match all three. **Both fix cycles verified this way, cleanly, both times.**
Full logs: `investigation/nondeterminism_evidence/`.

## 3.5 Hostile-reader pass — completed

`investigation/HOSTILE_READER_PASS.md`. `SCORECARD.md` read in full; `README.md`'s headline
zones — opening, the blocks Steps 1–2 of the baseline fix regenerated, the surrounding
summary paragraphs, and the closing — read in full, the rest spot-checked for absolute
language. One fix (a SCORECARD.md closing sentence readable as a whole-project claim rather
than a scorecard-scoped one); everything else checked holds against the corrected numbers.
Scope stated explicitly in that document: it did not re-read all 411 lines of README.md
outside the zones a hostile reader would target after seeing numbers move.

## 3.6 One-sentence test — completed, folded into 3.5

Every headline sentence identified in the hostile-reader pass was checked against being read
alone, out of context, as that pass's own method — this is the same check §40's "0 wrong
answers" failure taught this project to run, applied here rather than as a separate pass.
One failure found and fixed (the same SCORECARD.md sentence as 3.5); nothing else failed
this test in the zones checked.

---

## Summary

| step | status |
|---|---|
| 1 — coverage metric | **done** |
| 2 — truncation announcement | **done**, plus one extra instance found and fixed |
| 3.1 — staleness sweep | **done** |
| 3.2 — normative claims vs code | **done**, 13/13 hold |
| 3.3 — clean clone | **done** — one real defect found and fixed (scale-degradation skip guard), full suite and `run_all.py` both verified clean afterward |
| 3.4 — determinism ×3 | **done** — surfaced §0's defect as a side effect first; re-run cleanly after each of the two fixes |
| 3.5 — hostile reader | **done** — one fix |
| 3.6 — one-sentence test | **done**, folded into 3.5 |

**What was worse than expected, stated as the headline this document has carried since it
first stopped:** the frozen `matching/` cascade — the baseline every comparison in this
repository is measured against — was not deterministic under load, and fixing that surfaced
a second, adjacent defect in the same function. Both are now fixed, both fixes were
predicted before they were made and the predictions were checked against the outcome rather
than assumed, both predictions missed (the second one badly), and both misses are published
alongside the fixes rather than smoothed over. Three previously-published `Determinate`
results in the frozen-cascade comparison were never actually proven unique. That is now
corrected, and the correction is louder in this document than the fact that everything else
checked came back clean.
