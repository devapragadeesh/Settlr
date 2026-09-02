# Prediction, written before `resolver/enumerate_closures.py` is touched

`DECISIONS.md` §58 documented the defect and deferred the fix, requiring "its
own dated decision, its own committed-before-the-fix prediction, and its own
before/after pair, exactly as §49 and §50 each got." This is that prediction.
It is committed in its own commit, **before** the parameter change exists, so
the ordering is verifiable from `git log` rather than asserted. `DECISIONS.md`
§67 is the entry that accompanies it.

Every number below was produced by a script in this directory, run against the
**current, unfixed** code. Nothing here changes a solver parameter.

---

## 0. Correction to §58 first, because a wrong description of a defect must not
## survive into the writeup of its fix

§58 reports the reproduction as:

> `first diff at index 56: bank_index=56, both Verified, different composition`

**No composition ever changed.** `reproduce_58.py` re-runs that experiment —
three `resolve()` calls on the identical in-memory `Dataset`, every
enumeration instrumented — and compares *every field of every outcome*, not a
summary:

```
run 0/1/2: 59 outcomes, 54 enumerations, 2 truncating
           [(34, 'time_budget_exceeded'), (33, 'time_budget_exceeded')]
run0 == run1: False    run0 == run2: False    run1 == run2: False

line 56: type=Verified  differing fields=['rival_closure_count']  167 / 166 / 166
line 58: type=Verified  differing fields=['rival_closure_count']  133 / 130 / 132
```

The only field that moves is `rival_closure_count`, on exactly the two lines
whose enumeration hit the clock — a 1:1 correspondence. `composition` is
identical across all three runs on all 59 lines.

This is consistent with the code and §58's description was not:
`Verified.composition` is built from `claimed`, never from `closures`
(`resolve.py:_verify`); the enumeration there feeds only
`rival_closure_count` and `rival_count_is_lower_bound`; and `Reconstructed`
explicitly **does not consume**, so a tier-C truncation cannot propagate
through `state.consumed` into a later tier-B `claimed` set.

**This makes the defect narrower than §58 states, and the correction cuts
against the fix's importance rather than for it.** It is recorded because the
alternative is a fix whose writeup overstates what it repaired.

---

## 1. What truncates, measured across all 35 datasets

`measure_truncation.py` wraps `closing_subsets` and records, per enumeration,
the calling function and the enumerator's own status.

Two sweeps are preserved, deliberately, as §49 preserved its run A and run B:

| file | conditions |
|---|---|
| `sweep_A_contended.json` / `.log` | run concurrently with a `score_gst.py --all` pass |
| `sweep_B_clean.json` | run alone, and the source of every number below |

Sweep B, uncontended:

```
TOTAL _tier_c  time_budget_exceeded = 50
TOTAL _verify  time_budget_exceeded = 26
datasets with ANY time_budget_exceeded: 30 / 35
```

**`cap_reached` is far more common than the clock (5–14 per dataset) and is
NOT at risk.** With `num_workers = 1` and a fixed `random_seed`, CP-SAT's
solution *order* is reproducible, so the first `cap` solutions are the same
set on every run irrespective of the clock. Only the 76 `time_budget_exceeded`
enumerations are in play. This is a claim, and §2 tests it rather than
assuming it.

The five datasets with **zero** clock stops — predicted wholly unaffected:

```
datasets/A10_B100_Cmax          cap_reached=2
datasets/A20_B0_Cmax            cap_reached=10
datasets/A40_B50_Cmax           cap_reached=13
datasets_v2/A20_B50_Cmax        cap_reached=6
datasets_gst_holdout/A20_B100_Cmax_gst_holdout   cap_reached=0, all optimal
```

**The held-out GST dataset is in that list, and that matters for §64.** Its 54
enumerations all return `optimal`. §58's exposure does not reach it.

---

## 2. The model, and the two experiments that tested it BEFORE the fix

**Model.** Instability is confined to enumerations the wall clock cut off.
Within those, the flip-critical bit is `complete` (`status == OPTIMAL`), which
decides `Unresolved` vs `Reconstructed`/`Ambiguous` in `_tier_c`; the
descriptive quantities (`rival_closure_count`, `partial_candidates`,
`detail`) are the subset *count*, which is far more sensitive.

### Experiment A — `determinism_probe.py`, uncontended, 3 runs each

| dataset | predicted | clock stops | `cap_reached` | identical |
|---|---|---:|---:|---|
| `datasets/A40_B50_Cmax` | IDENTICAL | 0 | 13 | **True** |
| `datasets_gst_holdout/A20_B100_Cmax_gst_holdout` | IDENTICAL | 0 | 0 | **True** |
| `datasets/A20_Bnone_Cmax` | DIFFERS | 5 (all tier-C) | 8 | **True** |

Rows 1–2 confirm the `cap_reached` half of the model: a heavily
cap-truncated dataset is bit-identical across runs. **Row 3 falsified the
prediction I made for it.** The worst tier-C exposure in the corpus was stable
when the machine was idle.

### Experiment B — `contended_probe.py`, the same dataset, 6 concurrent resolver processes

```
run 0: 83.2s  clock stops=5  counts=[0, 27,  9, 31, 11]
run 1: 83.6s  clock stops=5  counts=[0, 27,  9, 34,  9]
run 2: 83.2s  clock stops=5  counts=[0, 27,  9, 34, 10]

IDENTICAL ACROSS 3 CONTENDED RUNS: False
  line  11 Unresolved   fields=['detail', 'partial_candidates']
  line  15 Unresolved   fields=['detail', 'partial_candidates']
```

Experiment A was not evidence of stability; it was evidence that an idle
machine's wall clock does not vary much. Under load the same dataset moves —
which is the defect, restated exactly.

**The finding that shapes the prediction: the outcome TYPE never flipped.**
In all twelve runs across three experiments (3 GST uncontended, 3 tier-C
uncontended, 3 tier-C contended, plus §58's original three), every line kept
its class. What moved was always a descriptive field of a line that had
already been decided: `rival_closure_count` on a `Verified`, and
`detail`/`partial_candidates` on an `Unresolved`.

The mechanism explains it. Once the clock stops, `complete=False` and
`_tier_c` returns `Unresolved(ENUMERATION_TRUNCATED)` unconditionally. Flipping
requires a pool that *completes* in one run and not another — a narrow band —
whereas the subset count varies continuously with available CPU. **`complete`
is the stable bit and the count is the unstable one, and only `complete`
reaches an outcome class.**

---

## 3. The prediction

Stated as falsifiable claims, strongest first. `max_deterministic_time = 10.0`
replaces `max_time_in_seconds = 10.0` at the single call site,
`resolver/enumerate_closures.py:93`.

1. **The five zero-clock-stop datasets are bit-identical before and after the
   fix**, including `datasets_gst_holdout/A20_B100_Cmax_gst_holdout`. Their
   enumerations never consult the budget. *Falsified by:* any diff on those
   five.
2. **No line changes its outcome CLASS on any dataset.** The before/after diff
   consists only of `rival_closure_count` on `Verified` lines and
   `detail`/`partial_candidates` on `Unresolved` lines. *Falsified by:* any
   `Verified`/`Reconstructed`/`Ambiguous`/`Unresolved`/`AttestationDiscrepancy`
   count moving on any dataset.
3. **No composition changes anywhere.** *Falsified by:* any `composition` diff.
4. **`corpus/oracle.py`'s measured candidate-set statistics DO move** on some
   of the 30 affected datasets — `mean_candidate_set_size` and
   `max_candidate_set_size` (`oracle.py:425-426`) are computed over
   `Unresolved.partial_candidates` (`oracle.py:339`), the field Experiment B
   showed moving. *Falsified by:* those statistics being identical everywhere,
   which would mean the fix changed nothing at all.
5. **No gate flips.** The one violation path reading a candidate set
   (`oracle.py:345`) is guarded by `candidate_set.complete`, which stays
   `False` on a truncated enumeration under either budget. *Falsified by:* any
   G-gate changing verdict.
6. **After the fix, three uncontended runs and one deliberately contended run
   of the affected datasets are byte-identical** — §49's verification standard,
   and the actual point of the change.

**What I do NOT predict.** Which direction any individual count moves.
`max_deterministic_time = 10.0` is not a claim of equivalent search to 10.0
wall-clock seconds — OR-Tools publishes no conversion, by design, which is why
the parameter exists. Whether 10.0 deterministic units reaches further or less
far than 10 seconds did on this machine is empirical, and §4 answers it.

**Confidence, honestly split.** Claims 1, 3 and 5 rest on the mechanism and I
hold them firmly. Claim 2 is the one to watch: it rests on `complete` being a
stable bit, which is *observed* across twelve runs and *argued* from the
narrowness of the completion band, not proven. A dataset whose pool completes
in ~10 units but not ~10 seconds would falsify it, and I have no way to rule
one out without running the fix. If claim 2 fails, it is reported as a miss —
per §49, whose own directional prediction was not confirmed and said so.

---

## 4. The chosen budget, and what would revisit it

`max_deterministic_time = 10.0`, matching `DEFAULT_TIME_BUDGET`'s current
numeric value, on §49's precedent: the simplest choice that preserves the
budget's order of magnitude without asserting an equivalent amount of search.

`DEFAULT_TIME_BUDGET`'s name and the `wall_seconds` field become
misnomers under a deterministic budget. Both are addressed in the fix commit,
not here.

**Revisit if:** the post-fix run shows the count of `time_budget_exceeded`
enumerations moving substantially in either direction (materially more than
76, or materially fewer), since that would mean 10.0 deterministic units is
not the same order of magnitude as the old budget and the fix silently
re-tuned the resolver's search depth while claiming only to stabilise it. That
count is recorded before and after and compared explicitly.

---

## 5. Downstream figures to recompute, named now rather than discovered later

- `corpus/oracle_results.json` / `corpus/ORACLE_RESULTS.md`
- `corpus/THREE_SYSTEMS.md`, `CLAIMS.md`, `SCORECARD.md`, `dashboard/data.json`
  (all via `run_all.py`)
- `corpus/GST_RESULTS.md` / `corpus/gst_results.json` — re-scored, since Phase
  A's regeneration used the unfixed budget
- `corpus/BANKSIDE_RESULTS.md` / `corpus/bankside_results.json`

**`corpus/GST_HOLDOUT_RESULTS.md` is NOT re-scored.** Per claim 1 the fix
cannot reach it — the held-out dataset has zero clock stops — and per §64/§65
it is rendered from saved JSON, never re-run. That claim is verified by
running the *unfixed* and *fixed* resolver over it and diffing, which is a
check on the fix rather than a re-scoring of the held-out result.

`corpus/baseline_results.json` is **not** affected: the frozen cascade's own
budget was fixed in §49, and `matching/` is untouched here.
