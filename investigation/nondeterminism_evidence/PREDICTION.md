# Prediction, written before matching/stage3_solver.py is touched

Per the task's Step 1.3. This file is committed in the same change as the fix
and the verification runs, not edited afterward — the ordering is the
evidence, per this repository's own standing convention (`DECISIONS.md` §39,
§45).

## Correction to `investigation/FINAL_GATE.md` §0 first

Re-comparing the two preserved runs just now, excluding the `detail` field
(which `corpus/baseline_old_engine.py`'s stdout printer drops — the version of
run B reconstructed from the process log never had it, so its absence is a
reconstruction artefact, not a real difference), the honest count is:

- **6 datasets** disagree on the outcome bucket itself
  (`Determinate`/`Ambiguous`/`Unresolved` counts):
  `A30_B100_Cmax`, `A40_B100_Cfifo`, `A60_B100_Cmax`,
  `datasets_v2/A20_B0_Cmax`, `datasets_v2/A40_B100_Cmax`,
  `datasets_v2/A60_B100_Cmax`.
- **4 more** agree on the outcome bucket but disagree on
  `mean_candidate_set_size` (the specific candidate sets found within a bucket
  differ): `datasets_v2/A20_B100_Cfifo`, `datasets_v2/A20_B100_Crandom0`,
  `datasets_v2/A40_B100_Crandom`, `datasets_v2/A40_B50_Cmax`.
- **10 of 30**, not the "8 of 30" `FINAL_GATE.md` reported. That report's count
  was taken from a diff that had not yet excluded the `detail`-field
  reconstruction artefact and undercounted the datasets that disagree only in
  candidate-set contents. Corrected here, before the fix, because a wrong
  count of the problem should not survive into the writeup of its fix.

Both full runs are preserved for the reconciliation in Step 3:
`investigation/nondeterminism_evidence/run_A_committed.json` (matches the
currently committed `corpus/baseline_results.json` exactly) and
`run_B_contended.json` (reconstructed from the process log of the run that
executed concurrently with an oracle scoring pass in this session).

## The prediction

**Directional prior: weak, and stated as weak.** The mechanism is that a
wall-clock budget under contention completes less real search than the same
budget uncontended, so a switch to `max_deterministic_time` should make the
result track the amount of *work* rather than the amount of *time*, and should
therefore land closer to whichever historical run did more actual search.

Run A was captured by a dedicated, otherwise-idle invocation of
`corpus/baseline_old_engine.py --all`, consistent with
`corpus/BASELINE_OLD_ENGINE.md`'s own protocol of running the frozen engine
alone. Run B was captured by a background process that this session
deliberately left running concurrently with an active oracle-scoring pass, and
that concurrency is *why* it was flagged as the contended one in
`FINAL_GATE.md`.

**This is exactly the shape `DECISIONS.md` §47 warns about: an inference
resting on a premise nobody independently verified — that A was less
contended than B — because it is written down and remembered rather than
measured.** No CPU-utilization log was captured for either run; the belief
rests on session memory of which commands were running when. Treated
accordingly:

- **Weak prediction, offered anyway because §1.3 asks for one rather than a
  refusal:** the stable, deterministic-budget result is more likely to
  resemble **run A** than **run B** on the 10 disagreeing datasets, because
  the deterministic budget removes the penalty contention imposed on B, and
  nothing in the fix removes any advantage A may have had.
- **What I do NOT have a basis to predict:** the exact outcome on any single
  one of the 10 datasets. CP-SAT's search order under `num_workers=1` is
  reproducible, but *how far* a 30.0-deterministic-time-unit budget reaches
  into that order, relative to how far a 30.0-wall-clock-second budget reached
  on a given machine at a given moment, is not something I can derive without
  running it.
- **What would falsify this:** the stable result matching run B, or matching
  neither A nor B. Either is reported as a miss, not reasoned away.

## The chosen deterministic budget

`max_deterministic_time = 30.0`, replacing `max_time_in_seconds = 30.0` at
both call sites (`matching/stage3_solver.py` lines ~177 and ~203).

**Reasoning, and its limits, stated plainly:** OR-Tools does not publish a
fixed conversion between deterministic-time units and wall-clock seconds — the
ratio is solver- and instance-dependent by design, which is the entire reason
`max_deterministic_time` exists. Keeping the same numeric value (30.0) is not
a claim that it produces an equivalent *amount* of search to the old 30.0s
wall-clock figure; it is the simplest choice that preserves the existing
budget's order of magnitude while removing its dependence on the clock, and
its adequacy is an empirical question Step 2 answers, not a theoretical one
this section can settle. If Step 2 shows enumerations hitting the
deterministic cap in a way that changes outcomes versus an uncapped run, that
is reported and the value revisited — not silently accepted.
