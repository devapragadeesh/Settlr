"""Run the FROZEN `matching/` cascade (81c04e0, unmodified) over the corpus.

    python3 corpus/baseline_old_engine.py --all

## The compatibility shim, and what it costs

`matching/loaders.py` is frozen and expects `bank_statement.csv` with columns
`utr, date, narration, amount`. The corpus bank file is the BANK's artefact and
uses `bank_reference, value_date, narration, amount`. So a projection is
required, and it is lossy in ways that must be separated from the corpus's own
difficulty when reading the results:

* **column rename only** for the bank file. Every line is kept, including the
  foreign credits, the foreign debits and the reversal debit -- the old engine
  gets the real file, not a filtered one, because "is this credit even ours?"
  is a question a reconciliation engine has to answer.
* **`settlement_report.csv` is not passed at all.** The old engine has no
  notion of an attestation as a separate artefact; it reads `settlement_utr`
  off the recon rows, which is the same PSP claim by a different route. That
  is a limitation OF THE OLD ENGINE, not of the shim, and it is why the
  contract splits the artefacts in the first place.
* nothing else is changed. `matching/` is not modified, imported-and-patched,
  or re-run with different parameters.

## Mapping the old outcomes onto the contract

The old engine returns `Determinate` / `Ambiguous` / `Unresolved`. Translating
those into contract outcomes is not bookkeeping -- it is the measurement:

| old | contract | why |
|---|---|---|
| `Determinate` on an ATTESTED line whose attested composition matches | `Verified` | a composition claim, corroborated by an independent amount |
| `Determinate` on an attested line whose composition DISAGREES | none constructible | the engine asserted a composition the attestation contradicts, with no contradiction recorded |
| `Determinate` on an UNATTESTED line | none constructible | `Reconstructed` needs unfiltered uniqueness AND cross-line exclusivity; the engine established neither |
| `Ambiguous` | `Ambiguous` | maps cleanly |
| `Unresolved` | `Unresolved` | maps cleanly |

**Rows the mapping cannot construct are the finding.** Every one is an
assignment the old engine made and the contract has no vocabulary for -- which
is exactly the claim `resolver_contract/RESOLVER_CONTRACT.md` §0 makes, turned
into a number.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from matching import run as run_cascade                        # noqa: E402
from matching.loaders import load                              # noqa: E402
from matching.model import Ambiguous, Determinate, Unresolved   # noqa: E402

DATASETS = ROOT / "corpus" / "datasets"


def project(dataset: Path, into: Path) -> Path:
    """Rename the bank columns. Nothing else. Every line is kept."""
    into.mkdir(parents=True, exist_ok=True)
    for name in ("recon_combined.json", "disputes.json", "erp_orders.csv",
                 "gstr2b.csv"):
        source = dataset / name
        if source.exists():
            shutil.copy(source, into / name)
    with (dataset / "bank_statement.csv").open(newline="") as handle:
        lines = list(csv.DictReader(handle))
    with (into / "bank_statement.csv").open("w", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=["utr", "date", "narration",
                                                    "amount"],
                                lineterminator="\n")
        writer.writeheader()
        for line in lines:
            writer.writerow({"utr": line["bank_reference"],
                             "date": line["value_date"],
                             "narration": line["narration"],
                             "amount": line["amount"]})
    return into


def measure(dataset: Path) -> dict:
    truth = json.loads((dataset / "ground_truth.json").read_text())
    with tempfile.TemporaryDirectory(prefix="baseline_") as tmp:
        result = run_cascade(dataset=load(project(dataset, Path(tmp) / "d")))

    by_line = {b["bank_line_index"]: b for b in truth["batches"]
               if b.get("bank_line_index") is not None}
    bank_truth = {line["line_index"]: line for line in truth["bank_lines"]}
    attested = set(truth["attestation"]["attested_settlement_ids"])
    determined = set(truth.get("determined_instances", []))
    attested_lines = {index for index, batch in by_line.items()
                      if batch["settlement_id"] in attested}

    outcomes = Counter()
    wrong_confident = []
    foreign_adopted = []
    unrepresentable = []
    rows_misplaced = 0
    determined_abstained = 0
    candidate_sizes: list[int] = []

    for item in sorted(result.stage3.reconstructions, key=lambda r: r.bank_index):
        index = item.bank_index
        resolution = item.resolution
        expected = by_line.get(index)
        kind = bank_truth.get(index, {}).get("kind", "unknown")

        if isinstance(resolution, Determinate):
            outcomes["Determinate"] += 1
            candidate_sizes.append(1)
            claimed = tuple(sorted(resolution.decomposition.row_ids))
            if expected is None:
                foreign_adopted.append(
                    {"bank_index": index, "kind": kind,
                     "rows_placed": len(claimed)})
                rows_misplaced += len(claimed)
                unrepresentable.append(
                    {"bank_index": index,
                     "why": "Determinate on a bank line that is not a "
                            f"settlement of ours (kind={kind})"})
            else:
                actual = tuple(sorted(expected["composition"]))
                if claimed != actual:
                    extra = sorted(set(claimed) - set(actual))
                    missing = sorted(set(actual) - set(claimed))
                    wrong_confident.append(
                        {"bank_index": index, "extra": len(extra),
                         "missing": len(missing)})
                    rows_misplaced += len(extra)
                if index not in attested_lines:
                    unrepresentable.append(
                        {"bank_index": index,
                         "why": "Determinate on an UNATTESTED line: the "
                                "contract has no outcome for a confident "
                                "composition with neither unfiltered "
                                "uniqueness nor cross-line exclusivity"})
                elif claimed != actual:
                    unrepresentable.append(
                        {"bank_index": index,
                         "why": "Determinate whose composition the attestation "
                                "contradicts, with no contradiction recorded"})
        elif isinstance(resolution, Ambiguous):
            outcomes["Ambiguous"] += 1
            candidate_sizes.append(len(resolution.candidates))
            if resolution.certain_rows:
                # D3: an assignment through a property that is not an
                # observation. The contract deletes this path entirely.
                unrepresentable.append(
                    {"bank_index": index,
                     "why": f"{len(resolution.certain_rows)} rows assigned via "
                            "Ambiguous.certain_rows -- an ambiguity PROPERTY "
                            "used as an assignment (defect D3)"})
            if index in determined:
                determined_abstained += 1
        else:
            outcomes["Unresolved"] += 1
            if index in determined:
                determined_abstained += 1

    return {
        "dataset": dataset.name,
        "axes": truth["axes"],
        "bank_lines": len(truth["bank_lines"]),
        "settlements": len(truth["batches"]),
        "outcomes": dict(outcomes),
        "confident_wrong_on_our_lines": len(wrong_confident),
        "foreign_lines_adopted": len(foreign_adopted),
        "foreign_lines_in_file": sum(1 for line in truth["bank_lines"]
                                     if line["kind"] != "settlement"),
        "rows_misplaced": rows_misplaced,
        "determined_instances": len(determined),
        "determined_abstained": determined_abstained,
        "unrepresentable_claims": len(unrepresentable),
        "mean_candidate_set_size": (sum(candidate_sizes) / len(candidate_sizes)
                                    if candidate_sizes else 0.0),
        "detail": {"wrong": wrong_confident[:8],
                   "foreign": foreign_adopted[:8],
                   "unrepresentable": unrepresentable[:8]},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs="?")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()

    targets = (sorted(p for p in DATASETS.iterdir() if p.is_dir())
               if arguments.all else [DATASETS / arguments.name])
    results = []
    for dataset in targets:
        if not (dataset / "ground_truth.json").exists():
            continue
        outcome = measure(dataset)
        results.append(outcome)
        print(json.dumps({k: v for k, v in outcome.items() if k != "detail"}))
    if arguments.out:
        arguments.out.write_text(json.dumps(results, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
