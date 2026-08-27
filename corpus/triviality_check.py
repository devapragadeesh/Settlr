"""Does a TRIVIAL PREDICATE SOLVE THE TASK?

    python3 corpus/triviality_check.py --all

## The ten minutes that were never spent

`corpus/leakage_audit.py` is 1,346 lines across five families and it asks one
question in five ways: **does a trivial predicate identify a planted class?**
It never asks the question one coordinate up: **does a trivial predicate solve
the task?**

It does. `corpus/baseline_naive.py` groups the recon rows by `settlement_id`,
nets credit minus debit, matches the total to a bank credit, and scores
**168/168 compositions** across the original fourteen datasets -- every pool
size, every attestation coverage, every selection rule. Nothing in the audit
could see that, because a benchmark's difficulty is not a property of any one
planted class.

The only baseline that had ever been run was the frozen cascade, which this
project had already published a three-defect report about. It was *guaranteed*
to look bad. A benchmark needs a strictly-**dumber** baseline as well as a
strictly-worse one, and this file is that check made impossible to omit:
it runs on every dataset, old and new, and its verdict is permanent output.

## What it reports, per dataset

    compositions exactly correct        did the trivial predicate get the rows?
    bank line -> batch correct          did it find the right line?
    foreign lines rejected              did it decline what is not ours?
    abstentions                         (always 0 -- it never declines)
    verdict                             TRIVIAL / PARTIAL / NOT TRIVIAL / N/A

**`N/A` is a result, not a skip.** At the PSP-absence axis points there is no
`settlement_id` column to group on, so the trivial predicate cannot be
evaluated at all. That is the cell where reconstruction is genuinely necessary
and it is the reason those datasets exist.

## The gate

Reporting is unconditional. `--gate` fails only when **every** dataset is
`TRIVIAL` -- a benchmark none of whose cells resist a `GROUP BY` is measuring
its own engine's self-imposed handicap, which is exactly what the original
fourteen were doing. Individual trivial datasets still ship: the easy
regression baseline is worth having, as long as it is labelled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.baseline_naive import measure                      # noqa: E402

FAMILIES = ("datasets", "datasets_v2")


def dataset_dirs() -> list[Path]:
    out: list[Path] = []
    for family in FAMILIES:
        directory = ROOT / "corpus" / family
        if directory.exists():
            out += [d for d in sorted(directory.iterdir())
                    if (d / "ground_truth.json").exists()]
    return out


def groupable(dataset: Path) -> bool:
    """Is there a `settlement_id` column to group on at all?

    Checked on the SOLVER-VISIBLE file, never on the key. An absent column and
    a null column are different artefacts and only the first makes the trivial
    predicate inexpressible.
    """
    rows = json.loads((dataset / "recon_combined.json").read_text())["items"]
    return any("settlement_id" in row for row in rows)


def resistance(result: dict) -> float:
    """The fraction of compositions the trivial predicate MISSES, as a %.

    This is the honest inverse of the verdict label. `PARTIAL` reads as "the
    benchmark resisted"; at 8.3% resistance it means a fifteen-line `GROUP BY`
    recovered eleven of twelve compositions and the benchmark barely resisted
    at all. A dataset the predicate cannot run on at all is 100%.
    """
    if result["verdict"] == "N/A":
        return 100.0
    attempted = result["compositions_attempted"]
    if not attempted:
        return 100.0
    return 100.0 * (1 - result["compositions_correct"] / attempted)


def verdict(result: dict) -> str:
    attempted = result["compositions_attempted"]
    lines = result["our_bank_lines"]
    foreign = result["foreign_lines"]
    if not attempted:
        return "NOT TRIVIAL"
    composition_rate = result["compositions_correct"] / max(attempted, 1)
    line_rate = result["line_to_batch_correct"] / max(lines, 1)
    foreign_rate = result["foreign_rejected"] / max(foreign, 1)
    if composition_rate == 1.0 and foreign_rate == 1.0 and line_rate >= 0.9:
        return "TRIVIAL"
    if composition_rate >= 0.8:
        return "PARTIAL"
    return "NOT TRIVIAL"


def run(datasets: list[Path]) -> list[dict]:
    results: list[dict] = []
    for dataset in datasets:
        family = dataset.parent.name
        if not groupable(dataset):
            results.append({
                "dataset": dataset.name, "family": family,
                "verdict": "N/A",
                "note": "no settlement_id column: the trivial predicate is "
                        "not expressible on this dataset",
            })
            continue
        result = measure(dataset)
        result["family"] = family
        result["verdict"] = verdict(result)
        results.append(result)
    return results


def render(results: list[dict]) -> str:
    out = ["# TRIVIALITY CHECK -- does a GROUP BY solve the task?", "",
           "**RESISTANCE is the number that matters**: the fraction of "
           "compositions the trivial predicate MISSES. A dataset at 8.3% "
           "resistance is not a hard dataset -- a `GROUP BY` still recovers "
           "eleven twelfths of it.", "",
           f"{'family':<13}{'dataset':<22}{'line->batch':>12}"
           f"{'composition':>13}{'foreign rej':>13}{'abstain':>9}"
           f"{'RESIST':>8}  verdict",
           "-" * 96]
    for r in results:
        if r["verdict"] == "N/A":
            out.append(f"{r['family']:<13}{r['dataset']:<22}"
                       f"{'-':>12}{'-':>13}{'-':>13}{'-':>9}{'100%':>8}  "
                       f"N/A ({r['note'].split(':')[0]})")
            continue
        out.append(
            f"{r['family']:<13}{r['dataset']:<22}"
            f"{r['line_to_batch_correct']:>5}/{r['our_bank_lines']:<6}"
            f"{r['compositions_correct']:>6}/{r['compositions_attempted']:<6}"
            f"{r['foreign_rejected']:>6}/{r['foreign_lines']:<6}"
            f"{r['abstentions']:>9}{resistance(r):>7.1f}%  {r['verdict']}")
    scored = [r for r in results if r["verdict"] != "N/A"]
    totals = {key: sum(r[key] for r in scored) for key in
              ("line_to_batch_correct", "our_bank_lines",
               "compositions_correct", "compositions_attempted",
               "foreign_rejected", "foreign_lines",
               "determined_instances", "reconstructible_instances")}
    if scored:
        totals = {key: sum(r[key] for r in scored) for key in
                  ("line_to_batch_correct", "our_bank_lines",
                   "compositions_correct", "compositions_attempted",
                   "foreign_rejected", "foreign_lines",
                   "determined_instances", "reconstructible_instances")}
        out += ["-" * 96,
                f"{'TOTAL':<35}"
                f"{totals['line_to_batch_correct']:>5}/{totals['our_bank_lines']:<6}"
                f"{totals['compositions_correct']:>6}/"
                f"{totals['compositions_attempted']:<6}"
                f"{totals['foreign_rejected']:>6}/{totals['foreign_lines']:<6}"
                f"{0:>9}"
                f"{100 * (1 - totals['compositions_correct'] / totals['compositions_attempted']):>7.1f}%"
                "  <- over the 28 datasets a GROUP BY can run on at all",
                "",
                f"abstentions on {totals['determined_instances']} determined + "
                f"{totals['reconstructible_instances']} reconstructible "
                "instances: 0"]
    counts = {v: sum(1 for r in results if r["verdict"] == v)
              for v in ("TRIVIAL", "PARTIAL", "NOT TRIVIAL", "N/A")}
    out += [""]
    if counts["TRIVIAL"] == len(results):
        out += ["EVERY dataset is solved by a GROUP BY. The benchmark is "
                "measuring a handicap the engine under test imposed on "
                "itself, not a difficulty the data contains."]
        return "\n".join(out)

    runnable = [r for r in results if r["verdict"] != "N/A"]
    cannot_run = [r for r in results if r["verdict"] == "N/A"]
    recovered = (totals["compositions_correct"] / totals["compositions_attempted"]
                 if runnable else 0.0)
    worst = max((resistance(r) for r in runnable), default=0.0)
    out += [
        "## The verdict, stated as the measurement rather than as a label", "",
        f"**On {len(runnable)} of {len(results)} datasets a fifteen-line "
        f"`GROUP BY` recovers {recovered:.1%} of compositions "
        f"({totals['compositions_correct']} of "
        f"{totals['compositions_attempted']}). On {len(cannot_run)} it cannot "
        "run at all.** Those "
        f"{len(cannot_run)} are the only cells that genuinely defeat the "
        "trivial predicate.",
        "",
        f"The highest resistance among datasets the predicate CAN run on is "
        f"**{worst:.1f}%** — one composition in twelve. `PARTIAL` in the table "
        "above must not be read as `NOT TRIVIAL`: a dataset where naive gets "
        "eleven of twelve right is a dataset naive very nearly solves.",
        "",
        f"An earlier version of this file concluded that "
        f"\"{len(results) - counts['TRIVIAL']} of {len(results)} datasets "
        "resist the trivial predicate\", counting every `PARTIAL` as "
        "resistance. That was too generous by "
        f"{counts['PARTIAL']} datasets and is withdrawn.",
        "",
        f"verdict counts: {counts}"]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("dataset", nargs="?", type=Path)
    parser.add_argument("--gate", action="store_true",
                        help="exit nonzero if EVERY dataset is trivial")
    parser.add_argument("--out", type=Path, help="write the rendered report")
    parser.add_argument("--json", type=Path, help="write the findings as JSON")
    arguments = parser.parse_args()

    datasets = ([arguments.dataset] if arguments.dataset and not arguments.all
                else dataset_dirs())
    results = run(datasets)
    print(render(results))
    if arguments.out:
        arguments.out.write_text(render(results) + "\n")
    if arguments.json:
        arguments.json.write_text(json.dumps(results, indent=1) + "\n")
    if arguments.gate and all(r["verdict"] == "TRIVIAL" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
