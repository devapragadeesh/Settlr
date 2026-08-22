"""Multi-seed robustness sweep.

The dataset is a pure function of one integer. A commit timestamp cannot
detect seed-shopping -- trying seeds until the numbers look good. What CAN
rule it out is showing that the properties hold across seeds nobody chose.

Writes ROBUSTNESS.md. Slow (a few seconds per seed); not part of the default
test run.

Run:  python3 engine/robustness.py [--seeds 20]
"""

from __future__ import annotations

import argparse
import statistics
import tempfile
from collections import Counter
from pathlib import Path

import generator

ROOT = Path(__file__).resolve().parent


def sweep(seeds: list[int]):
    results = []
    for seed in seeds:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows, result, labels, batch_labels, counts = generator.generate(
                seed, tmp / "data", tmp / "truth")
        tiers = Counter(r["source_tier"] for r in rows)
        results.append({
            "seed": seed,
            "rows": len(rows),
            "batches": len(result.batches),
            "ambiguous": sum(1 for b in result.batches if b.ambiguous),
            "counts": counts,
            "tiers": tiers,
        })
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    args = ap.parse_args()

    seeds = list(range(args.seeds))
    results = sweep(seeds)
    classes = sorted({name for r in results for name in r["counts"]})

    out = ["# ROBUSTNESS.md\n",
           "## Why this file exists\n",
           "The dataset is a pure function of one integer. A git timestamp proves the",
           "bytes existed at time T; it cannot prove nobody tried seeds until the",
           "numbers looked good. **This table is the answer to that attack**: the same",
           f"generator, run over seeds `0..{args.seeds - 1}` — a contiguous range, not a",
           "selection — produces the same structure with the same classes present.\n",
           "## What the shipped seed WAS selected for\n",
           "Stating this plainly, because omitting it would be the dishonest version.",
           "Seed `20260822` was picked from a sweep under exactly two constraints:\n",
           "1. the dataset lands on **exactly 240 rows**;",
           "2. **at least two** batches come out provably ambiguous.\n",
           "Nothing else was selected for, and nothing else *could* have been: at the",
           "time of selection no solver existed, so no accuracy, match-rate or",
           "solvability property was observable. The table below is what shows that",
           "those two constraints are ordinary draws rather than a lucky corner.\n",
           "## Class counts across seeds\n",
           "| class | min | median | max | seeds with zero |",
           "|---|---:|---:|---:|---:|"]

    for name in classes:
        series = [r["counts"].get(name, 0) for r in results]
        zeros = sum(1 for v in series if v == 0)
        flag = f"**{zeros}**" if zeros else "0"
        out.append(f"| `{name}` | {min(series)} | {int(statistics.median(series))} "
                   f"| {max(series)} | {flag} |")

    rows = [r["rows"] for r in results]
    batches = [r["batches"] for r in results]
    amb = [r["ambiguous"] for r in results]
    out += ["",
            "## Shape\n",
            "| quantity | min | median | max |",
            "|---|---:|---:|---:|",
            f"| recon rows | {min(rows)} | {int(statistics.median(rows))} | {max(rows)} |",
            f"| batches | {min(batches)} | {int(statistics.median(batches))} "
            f"| {max(batches)} |",
            f"| ambiguous batches | {min(amb)} | {int(statistics.median(amb))} "
            f"| {max(amb)} |",
            "",
            "## Reading this table\n",
            "A class whose **seeds with zero** column is non-zero is a class the",
            "generator cannot deliver on every seed. Those are named here rather than",
            "hidden: the generator records every missed plant in the ground-truth key",
            "as `planted: false` with a reason, instead of quietly shipping a smaller",
            "dataset and letting the class count drift.\n",
            "**Ambiguity is the one class that is not always reachable.** It requires a",
            "sum below the live-balance cap that two distinct subsets of the eligible",
            "pool both hit; on some ledgers no such sum exists. That is a property of",
            "the rule, not a defect in the generator, and it is why the shipped seed",
            "was constrained to produce at least two.\n",
            "Row count varies by seed because planting inserts a variable number of",
            "calibration debits.\n"]

    (ROOT / "ROBUSTNESS.md").write_text("\n".join(out) + "\n")
    print(f"wrote {ROOT / 'ROBUSTNESS.md'} over {len(seeds)} seeds")


if __name__ == "__main__":
    main()
