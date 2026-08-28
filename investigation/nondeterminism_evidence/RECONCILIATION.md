# Reconciliation — the stable, deterministic-budget baseline against the prediction and the two historical draws

Step 3 of the `max_deterministic_time` fix (`PREDICTION.md`, `investigation/FINAL_GATE.md`).
The stable run referenced throughout is the output of three consecutive uncontended
executions of `corpus/baseline_old_engine.py --all`, confirmed byte-identical to each
other (excluding wall-clock `seconds`) and confirmed to still match under a fourth,
deliberately contended execution (`corpus/score_resolver.py --all` running concurrently).
That determinism verification is not re-derived here — see `investigation/FINAL_GATE.md`
for the check itself. This document reconciles what that stable output *is* against what
was predicted and against what was previously published.

## 1.1 — Against the prediction, miss first

**The prediction is not confirmed. Lead with that.**

`PREDICTION.md` offered a weak, explicitly-flagged-as-unverified lean toward run A on the
10 datasets where A and B (the two wall-clock draws) had been observed to disagree. The
falsifiers it named were "the stable result matching run B, or matching neither A nor B."
Both happened:

| outcome vs. the two historical draws | count | datasets |
|---|---:|---|
| stable matches **A**, B differs | 2 | `A60_B100_Cmax`, `datasets_v2/A60_B100_Cmax` |
| stable matches **B**, A differs | 2 | `A30_B100_Cmax`, `A40_B100_Cfifo` |
| stable matches **neither** — A and B had *agreed* with each other, stable breaks with both | 4 | `A40_B100_Cmax`, `A40_B100_Crandom`, `datasets_v2/A20_B100_Crandom0`, `datasets_v2/A20_B75_Cmax` |
| stable matches **neither** — all three differ from each other | 2 | `datasets_v2/A20_B0_Cmax`, `datasets_v2/A40_B100_Cmax` |

Of the 10 datasets carrying any outcome-bucket disagreement across `{A, B, stable}`: **2
lean toward A, 2 toward B, 6 toward neither.** The predicted directional lean toward A is
not supported — it is outnumbered by "matches neither" alone, before B is even counted.

**The more interesting result, and the one that actually leads:** four of those six
"matches neither" cases are *new* divergences that the original two-run comparison in
`FINAL_GATE.md` could never have surfaced, because A and B happened to agree with each
other on those four datasets. The deterministic-time fix does not just resolve which of
two previously-seen states is "real" — it produces a *third* state that neither wall-clock
draw reached. This is the expected shape once the mechanism is stated plainly: a wall-clock
budget under a variable-speed CPU does not sample from a two-point space {A, B}; it samples
from a continuum of truncation points, of which A and B were two arbitrary draws and the
deterministic-time result is a third. Two historical runs agreeing with each other was never
evidence that they had found the "true" answer — it was evidence only that they happened to
truncate the search at a similar point. `A40_B100_Cmax` and `A40_B100_Crandom` show this
concretely: A and B are bit-for-bit identical on outcome counts, and the stable run still
differs from both.

**What was NOT predictable and is not being retroactively explained:** the prediction said
plainly it had no basis to call the outcome on any single dataset, and it does not do so
here either — the table above is a report of what happened, not a re-derivation of why this
specific set of 6 (rather than some other split) landed where it did. `PREDICTION.md`'s
unverified premise (that A was less contended than B) is neither confirmed nor refuted by
this data; the result is equally consistent with A and B simply having hit two different,
arbitrary points on the truncation continuum, contention aside.

## 1.2 — Full reconciliation against the committed baseline, every dataset

`corpus/baseline_results.json` (pre-fix) is bit-for-bit identical to
`investigation/nondeterminism_evidence/run_A_committed.json` (verified directly, excluding
`seconds`) — the committed baseline was run A. The table below is the complete,
dataset-by-dataset diff of every field against the stable run; nothing is summarized or
omitted.

Two unrelated causes are mixed in this diff and are called out separately below the table:
(1) the actual determinism-fix effect (`outcomes`, `mean_candidate_set_size`, and the counts
derived from them), and (2) `detail_truncated`/`detail_total` reading `None` in the old file
on 28 of 30 datasets — this is *not* an effect of this fix. Those two fields were added to
`corpus/baseline_old_engine.py`'s output schema by the truncation-announcement work earlier
in this phase (commit `2eb6c91`), and `corpus/baseline_results.json` was never re-run since
that schema change landed — it was stale before this fix touched anything. Regenerating the
baseline as part of this reconciliation is what backfills those fields; it is a side effect
of finally re-running the file, not a finding about determinism.

### Datasets with an outcome-bucket change (the determinism-fix effect, 10 of 30)

| dataset | committed (`outcomes`) | stable (`outcomes`) | mean candidate set size (committed → stable) |
|---|---|---|---|
| `A30_B100_Cmax` | Det 4 / Amb 6 / Unres 10 | Det 4 / Amb 7 / Unres 9 | 14.1 → 14.0 |
| `A40_B100_Cfifo` | Det 4 / Amb 7 / Unres 9 | Det 5 / Amb 7 / Unres 8 | 20.0 → 16.17 |
| `A40_B100_Cmax` | Det 1 / Amb 14 / Unres 5 | Det 1 / Amb 12 / Unres 7 | 22.67 → 21.92 |
| `A40_B100_Crandom` | Det 2 / Amb 9 / Unres 9 | Det 2 / Amb 8 / Unres 10 | 24.09 → 22.1 |
| `A60_B100_Cmax` | Det 1 / Amb 7 / Unres 12 | Det 1 / Amb 7 / Unres 12 (mccs moved only) | 20.0 → 17.875 |
| `datasets_v2/A20_B0_Cmax` | Det 4 / Amb 9 / Unres 7 | Det 4 / Amb 7 / Unres 9 | 20.54 → 20.73 |
| `datasets_v2/A20_B75_Cmax` | Det 4 / Amb 8 / Unres 8 | Det 4 / Amb 7 / Unres 9 | 12.08 → 10.18 |
| `datasets_v2/A20_B100_Crandom0` | Det 2 / Amb 10 / Unres 8 | Det 2 / Amb 9 / Unres 9 | 19.0 → 19.36 |
| `datasets_v2/A40_B100_Cmax` | Det 2 / Amb 9 / Unres 9 | Det 3 / Amb 8 / Unres 9 | 23.64 → 22.36 |
| `datasets_v2/A60_B100_Cmax` | Det 1 / Amb 13 / Unres 6 | Det 1 / Amb 13 / Unres 6 (mccs moved only) | 25.64 → 25.79 |

`A60_B100_Cmax` and `datasets_v2/A60_B100_Cmax` are listed here (not just in the
mean-candidate-set-size table below) because they were part of the original 10-way A/B
disagreement in `PREDICTION.md`, even though their outcome *bucket counts* happen to match
the committed file — only `mean_candidate_set_size` (i.e., which specific candidate sets
were found within the same bucket totals) moved.

Every other field that changes alongside an outcome-bucket change (`unrepresentable_claims`,
`determined_abstained`) is a mechanical consequence of the bucket counts changing, not an
independent finding: on `A30_B100_Cmax`, `A40_B100_Cfifo`, `A40_B100_Cmax`,
`A40_B100_Crandom`, `datasets_v2/A20_B0_Cmax`, and `datasets_v2/A20_B100_Crandom0`,
`unrepresentable_claims` shifts by exactly the same amount the `Ambiguous`/`Determinate`
split shifts.

### Datasets with only `mean_candidate_set_size` changed, outcome bucket identical (8 of 30)

`A10_B100_Cmax` — unchanged; `A20_B100_Cmax` (6.92 → 6.42), `datasets_v2/A20_B100_Cfifo`
(16.0 → 15.85), `datasets_v2/A40_B100_Cfifo` (18.0 → 17.29), `datasets_v2/A40_B100_Crandom`
(27.2 → 25.9), `A20_B0_Cmax` (23.21 → 21.36, `unrepresentable_claims` 4→6),
`A40_B50_Cmax` (22.0 → 21.0, `unrepresentable_claims` 5→6). These are cases where the same
candidate sets were not enumerated in the same order or count within an unchanged bucket
total — the search reached a different point in its own space without crossing a bucket
boundary.

### Datasets unaffected by anything in this fix (2 of 30)

`A20_Bnone_Cmax` and `A40_Bnone_Cmax` — the two PSP-absence datasets — are byte-identical
to the committed file in every field, including `mean_candidate_set_size`. Both have no
`settlement_id` column at all, so the pools involved are small and shallow enough that no
observed budget (wall-clock or deterministic) has ever cut a search short on them.

### `detail_truncated` / `detail_total` (schema backfill, not a fix effect)

All 30 datasets gain populated `detail_truncated`/`detail_total` fields, since the old file
predates that schema. One value here is worth flagging on its own terms, independent of the
determinism fix: `A20_B50_Cmax` reports `detail_truncated: true` — this is the dataset where
Step 2's `truncated`-flag finding (see `DECISIONS.md` §50 once filed) will actually matter;
it is the one case in this run where the enumerator hit its cap on at least one bank line.

## An incidental bug found while regenerating `THREE_SYSTEMS.md`

Re-running `corpus/three_systems.py` against the corrected baseline crashed:
`_totals()` computed `out["contradicted"]` by iterating `ran` (a list of
per-dataset sub-dicts, e.g. the dict returned by `frozen_row`) but re-used the
loop variable name `r` and indexed it with `r[system]` a second time — code
that is only correct when `r` is still the *row*, not the sub-dict `ran`
already reduced it to. This is unrelated to the determinism fix; it is a
pre-existing bug in the `record_contradicted` column that was added to
`three_systems.py` at some point after `corpus/THREE_SYSTEMS.md` and
`README.md` were last regenerated, and it means **that column had never
successfully rendered even once** — every "coverage N/M (P%)" figure with no
"record-contradicted" suffix currently published for the frozen cascade and
the resolver predates the three-way coverage split entirely, not just the
baseline fix. Fixed with a one-line change (`item.get(...)` instead of
`r[system].get(...)`, since `item` — renamed from the shadowing `r` — already
*is* the per-system dict). This is why the resolver's coverage figures in
`THREE_SYSTEMS.md`/`README.md` change format (`143/168 (85%)` →
`143/143 (100%), 25 record-contradicted`) in the same diff as the frozen
cascade's baseline-fix numbers — two different, unrelated causes landing in
the same regeneration because the file had not been regenerated since either
one took effect. The frozen cascade's own coverage counts move because of the
baseline fix specifically: original 14, **56/168 → 57/168** (55/56 → 56/57
correct); false-attestation 14, **50/167 → 51/167** (48/50 → 49/51 correct).
PSP-absence is untouched (the frozen cascade cannot run there either way).

## What replaces what

`corpus/baseline_results.json` is replaced with the verified-stable run (confirmed
byte-identical across three uncontended executions and matching a fourth, contended one).
The pre-fix file is preserved, not discarded, at
`corpus/baseline_results_predeterminism.json` — the before/after pair is the evidence, per
the standard `DECISIONS.md` §39 set.
