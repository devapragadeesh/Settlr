"""The trivial baseline. It scores 168/168, and that is the corpus's most
important finding about itself.

    python3 corpus/baseline_naive.py

## What this does

Fifteen lines of logic, no solver, no enumeration, no contract:

    group the recon rows by `settlement_id`      -> the composition
    net credit - debit within each group          -> the payout
    match that payout against a bank credit       -> the bank line

That is the "group by `settlement_id` and check the total" approach that
`DECISIONS.md` §1 explicitly rejected as *"one line of code and what the recon
file invites"*, on the grounds that it makes ambiguity structurally invisible.

## Why it had to be written, and why it was not

`corpus/baseline_old_engine.py` runs the frozen cascade -- an engine this
project had already published a three-defect report about. It was **guaranteed
to look bad**. Running only a baseline you already know will fail tells you
nothing about whether the benchmark is measuring difficulty or manufacturing
it. This is the strictly-*worse* baseline; a benchmark also needs a
strictly-*dumber* one, and that omission is the single largest methodological
error of the corpus phase.

## What it measures, and what that means

Measured across all 14 datasets, 280 bank lines:

    compositions exactly correct                168 / 168
    bank line -> batch correct                  168 / 182
    foreign lines correctly rejected             98 /  98
    abstentions on determined instances           0 /  88
    abstentions on reconstructible instances      0 /  31

Invariant across pool size 10 -> 60, attestation coverage 100% -> 0%, and all
three selection rules.

**Because `settlement_id` is populated on every settled row of every dataset,
and the corpus never once plants a FALSE `settlement_id`.** The 13 planted
`wrong_attestations` corrupt a scalar in `settlement_report.csv`; not one of
them assigns a row to the wrong batch. So a resolver that simply trusts the PSP
is perfectly calibrated here, and the corpus cannot distinguish it from a sound
one.

The consequences are not small:

* **Axis A does not measure difficulty.** The closure collapse from 12/12
  unique at pool 10 to 3/12 at pool 52 is real arithmetic, but it is only
  *binding* on a solver that has withheld `settlement_id` from itself
  (`matching/stage3_solver.py`'s `WITHHELD`). The difficulty is constructed.
* **Axis B does not remove the composition claim.** Coverage varies the
  bank-line -> batch *reference*. `settlement_id` on the rows is at 100% in
  every cell, including `A20_B0_Cmax`.
* **"Abstained on 49 of 88" is measured against a bar a `GROUP BY` clears.**

The epistemic argument for withholding the attestation is still sound -- an
attestation is a claim and claims can be wrong. But **this corpus never makes
one false**, so the argument is untested here, and a benchmark that cannot
falsify the premise it is built on has not yet earned its conclusions.

The fix is one planted class: a batch whose `settlement_id` names rows that are
not its true composition, where the arithmetic still closes. See
`corpus/CORPUS_SPEC.md` §8.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATASETS = ROOT / "corpus" / "datasets"


def paise(text: str) -> int:
    """Rupee string -> integer paise. Never float division."""
    text = text.strip()
    negative = text.startswith("-")
    whole, _, frac = text.lstrip("-").partition(".")
    value = int(whole) * 100 + int((frac + "00")[:2])
    return -value if negative else value


def measure(dataset: Path) -> dict:
    truth = json.loads((dataset / "ground_truth.json").read_text())
    rows = json.loads((dataset / "recon_combined.json").read_text())["items"]
    with (dataset / "bank_statement.csv").open(newline="") as handle:
        bank = list(csv.DictReader(handle))

    by_id = {row["entity_id"]: row for row in rows}
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for row in rows:
        if row.get("settlement_id"):
            groups[row["settlement_id"]].append(row["entity_id"])
    net = {sid: sum(by_id[e]["credit"] - by_id[e]["debit"] for e in ids)
           for sid, ids in groups.items()}
    by_amount: dict[int, list[str]] = collections.defaultdict(list)
    for sid, value in net.items():
        by_amount[value].append(sid)

    true_line = {b["line_index"]: b["true_settlement_id"]
                 for b in truth["bank_lines"]}
    true_comp = {b["settlement_id"]: sorted(b["composition"])
                 for b in truth["batches"]}

    ours = correct_line = correct_comp = attempted = 0
    foreign = foreign_rejected = 0
    for index, line in enumerate(bank):
        candidates = by_amount.get(paise(line["amount"]), [])
        claimed = candidates[0] if len(candidates) == 1 else None
        actual = true_line.get(index)
        if actual is None:
            foreign += 1
            foreign_rejected += claimed is None
            continue
        ours += 1
        if claimed == actual:
            correct_line += 1
            attempted += 1
            correct_comp += sorted(groups[claimed]) == true_comp[actual]

    from corpus.oracle import reconstructible_instances
    return {
        "dataset": dataset.name,
        "our_bank_lines": ours,
        "line_to_batch_correct": correct_line,
        "compositions_attempted": attempted,
        "compositions_correct": correct_comp,
        "foreign_lines": foreign,
        "foreign_rejected": foreign_rejected,
        "determined_instances": len(truth.get("determined_instances", [])),
        "reconstructible_instances": len(reconstructible_instances(truth)),
        "abstentions": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()

    results = [measure(d) for d in sorted(DATASETS.iterdir())
               if (d / "ground_truth.json").exists()]
    total = lambda key: sum(r[key] for r in results)

    print(f"{'dataset':<22}{'line->batch':>12}{'composition':>13}"
          f"{'foreign rej':>13}{'abstain':>9}")
    for r in results:
        print(f"{r['dataset']:<22}"
              f"{r['line_to_batch_correct']:>5}/{r['our_bank_lines']:<6}"
              f"{r['compositions_correct']:>6}/{r['compositions_attempted']:<6}"
              f"{r['foreign_rejected']:>6}/{r['foreign_lines']:<6}"
              f"{r['abstentions']:>9}")
    print("-" * 69)
    print(f"{'TOTAL':<22}{total('line_to_batch_correct'):>5}/{total('our_bank_lines'):<6}"
          f"{total('compositions_correct'):>6}/{total('compositions_attempted'):<6}"
          f"{total('foreign_rejected'):>6}/{total('foreign_lines'):<6}"
          f"{0:>9}")
    print()
    print(f"abstentions on {total('determined_instances')} determined + "
          f"{total('reconstructible_instances')} reconstructible instances: 0")
    print()
    print("A resolver that TRUSTS the PSP is perfectly calibrated on this")
    print("corpus, because the corpus never plants a false settlement_id.")
    print("That is a defect in the corpus. See the module docstring.")

    if arguments.out:
        arguments.out.write_text(json.dumps(results, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
