"""Diagnostic only. Nothing in `resolver/` is touched.

D15's mechanism: at PSP absence, no line ever attests, so every credit falls
to `_tier_c`. Only `Verified` calls `state.consumed.update(...)`
(`resolver/resolve.py:801`, the one call site) -- `Reconstructed` deliberately
does not, per contract sec 2.4 / `may_consume()`
(`resolver_contract/types.py:977-985`): "Only `Verified` removes rows from
later pools... an ambiguity is not a reason to believe the rows are spent."

That stated reason is about AMBIGUITY. `Reconstructed` is not ambiguous by
construction -- `Reconstructed.__post_init__` already requires
`UNIQUE_CLOSURE_UNFILTERED` (exhaustive, unbiased -- no objective, contract
sec 2.1) plus `CROSS_LINE_EXCLUSIVITY`, and explicitly rejects construction if
independent corroboration exists (that would make it `Verified` instead). So
the stated justification for withholding consumption does not obviously reach
`Reconstructed`'s own case, unlike D2 in the OLD `matching/` cascade, where
`Determinate` was reachable WITHOUT genuine uniqueness (D1: "unique among
subsets maximising applied debits", not unique overall) -- that gap, not
ambiguity itself, is what let D2's consumption ship a confident wrong answer.

**A hand proof, and the hole found in it.** If `pool_at`'s superset guarantee
holds (never wrongly excludes a row -- reaffirmed by F1/DECISIONS sec 45) and
lines are processed in true chronological order, then by induction the FIRST
line to report `Reconstructed` must be correct (its true composition's rows
were never falsely removed, so if exactly one candidate closes, that
candidate must be the truth -- otherwise the truth would be a second,
distinct candidate, contradicting count==1). Consuming it immediately can
then only shrink later lines' pools toward the truth, never away from it, so
the induction should carry forward.

**The hole**: `resolve()` sorts credits by `(value_date, line.index)`
(resolve.py:239) -- SAME-DATE lines are ordered by an arbitrary index
tiebreak, not by true settlement order. If two same-day lines' true
compositions overlap in candidate rows, processing them in the wrong relative
order could let the first one eagerly (and wrongly) claim a row the second
one's TRUE composition needed -- silently, since the row just vanishes from
the second line's pool. `resolver/resolve.py::_resolve_collisions`'s own
docstring says two `Reconstructed` claims colliding on a row "only showed up
when the resolver was first run across the whole corpus" under the CURRENT
non-consuming regime -- empirical evidence the tie risk is real, not just
theoretical.

This script measures, not assumes: does eager `Reconstructed` consumption
(chronological, in-line, no same-day guard) ever produce a WRONG assignment
anywhere in the 35-dataset corpus, and does it recover any of D15's 15
correct-refusal lines without doing so?

    python3 investigation/d15_joint_reasoning/track_eager_reconstruction.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import resolver.resolve as R                                         # noqa: E402
from resolver.loaders import load                                    # noqa: E402
from resolver_contract.types import Reconstructed                    # noqa: E402

FAMILIES = ("datasets", "datasets_v2", "datasets_gst", "datasets_bankside")
HERE = Path(__file__).resolve().parent

_original_tier_c = R._tier_c


def _eager_tier_c(line, dataset, state, cap, time_budget):
    """Wraps `_tier_c` unmodified, then consumes on `Reconstructed` --
    the one-line change this diagnostic is measuring the safety of.
    `state` is the same mutable `_State` the main loop already threads
    through every call, so this is visible to every later line in the same
    `resolve()` run with no other code touched."""
    outcome = _original_tier_c(line, dataset, state, cap, time_budget)
    if isinstance(outcome, Reconstructed):
        state.consumed.update(outcome.assigned_rows)
    return outcome


def dataset_dirs() -> list[Path]:
    out: list[Path] = []
    for family in FAMILIES:
        directory = REPO / "corpus" / family
        if directory.exists():
            out += [d for d in sorted(directory.iterdir())
                    if (d / "recon_combined.json").exists()]
    return out


def _truth_by_line(truth: dict) -> dict[int, dict]:
    return {batch["bank_line_index"]: batch for batch in truth["batches"]
            if batch.get("bank_line_index") is not None}


def _check(name: str, directory: Path, before_outcomes, after_outcomes,
           truth_by_line: dict[int, dict]) -> dict:
    before_by_line = {o.bank_index: o for o in before_outcomes}
    after_by_line = {o.bank_index: o for o in after_outcomes}
    changed = []
    wrong = []
    for bank_index, after in after_by_line.items():
        before = before_by_line[bank_index]
        if type(before).__name__ == type(after).__name__:
            continue
        entry = {"bank_index": bank_index,
                 "before": type(before).__name__,
                 "after": type(after).__name__}
        changed.append(entry)
        if type(after).__name__ in ("Reconstructed", "Verified"):
            truth = truth_by_line.get(bank_index)
            claimed = sorted(after.assigned_rows)
            true_rows = sorted(truth["composition"]) if truth else None
            if true_rows is None or claimed != true_rows:
                wrong.append({**entry, "claimed": claimed,
                             "true_composition": true_rows})
    return {"dataset": name, "changed": changed, "wrong": wrong}


def main() -> int:
    report = []
    total_changed = total_wrong = total_recovered_correct = 0
    for directory in dataset_dirs():
        name = f"{directory.parent.name}/{directory.name}"
        truth = json.loads((directory / "ground_truth.json").read_text())
        truth_by_line = _truth_by_line(truth)

        dataset = load(directory)
        before = R.resolve(dataset).line_outcomes

        R._tier_c = _eager_tier_c
        try:
            dataset2 = load(directory)
            after = R.resolve(dataset2).line_outcomes
        finally:
            R._tier_c = _original_tier_c

        result = _check(name, directory, before, after, truth_by_line)
        report.append(result)
        n_changed = len(result["changed"])
        n_wrong = len(result["wrong"])
        n_recovered_correct = n_changed - n_wrong
        total_changed += n_changed
        total_wrong += n_wrong
        total_recovered_correct += n_recovered_correct
        flag = " <-- WRONG ANSWER PRODUCED" if n_wrong else ""
        print(f"{name:<48} changed={n_changed:>3} "
              f"correct_recoveries={n_recovered_correct:>3} "
              f"wrong={n_wrong:>3}{flag}", flush=True)

    out = HERE / "eager_reconstruction_report.json"
    out.write_text(json.dumps(report, indent=1, sort_keys=True))
    print(f"\ntotal outcome-class changes: {total_changed}")
    print(f"total CORRECT recoveries (Reconstructed/Verified matching truth): "
          f"{total_recovered_correct}")
    print(f"total WRONG answers introduced: {total_wrong}")
    print(f"wrote {out}")
    return 1 if total_wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
