"""Run the resolver over one or more corpus datasets.

    python3 -m resolver.run --all
    python3 -m resolver.run corpus/datasets/A20_B100_Cmax

Prints the contract's six-way accounting -- **not** a match rate -- including
mean and max candidate set size, always and unprompted. Without those,
"declined fewer lines" and "enumerated more candidates until the truth was
somewhere in the set" are indistinguishable, and only the first is skill.

THIS MODULE DOES NOT SCORE. Scoring needs the answer key, so it lives in
`corpus/score_resolver.py`, on the far side of the isolation boundary. The
split is the point: nothing under `resolver/` can read a `ground_truth.json`,
and `resolver/tests/test_isolation.py` fails if that ever changes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resolver.loaders import load                       # noqa: E402
from resolver.resolve import NAME, resolve              # noqa: E402

FAMILIES = ("datasets", "datasets_v2")


def dataset_dirs() -> list[Path]:
    out: list[Path] = []
    for family in FAMILIES:
        directory = ROOT / "corpus" / family
        if directory.exists():
            out += [d for d in sorted(directory.iterdir())
                    if (d / "recon_combined.json").exists()]
    return out


def run_one(directory: Path) -> tuple[object, float]:
    began = time.perf_counter()
    output = resolve(load(directory))
    return output, time.perf_counter() - began


def summarise(output, seconds: float) -> dict:
    accounting = output.accounting()
    return {
        "dataset": output.dataset,
        "verified": accounting.verified,
        "verified_non_decisive": accounting.verified_non_decisive,
        "attestation_discrepancy": accounting.attestation_discrepancy,
        "reconstructed": accounting.reconstructed,
        "ambiguous": accounting.ambiguous,
        "unresolved": accounting.unresolved,
        "proven_unmatched": accounting.proven_unmatched,
        "open_breaks": accounting.open_breaks,
        "incomplete_enumerations": accounting.incomplete_enumerations,
        "mean_candidate_set_size": round(accounting.mean_candidate_set_size, 3),
        "max_candidate_set_size": accounting.max_candidate_set_size,
        "unresolved_by_reason": accounting.reasons.get("unresolved", {}),
        "discrepancy_by_kind": accounting.reasons.get(
            "attestation_discrepancy", {}),
        "rows_assigned": len(output.row_assignments),
        "seconds": round(seconds, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dataset", nargs="?", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--json", type=Path)
    arguments = parser.parse_args()

    targets = ([arguments.dataset] if arguments.dataset and not arguments.all
               else dataset_dirs())
    results = []
    print(f"# {NAME}", "")
    header = (f"{'dataset':<34}{'V':>4}{'AD':>4}{'R':>4}{'Amb':>5}{'Unr':>5}"
              f"{'mean k':>9}{'max k':>7}{'rows':>7}{'sec':>7}")
    print(header)
    print("-" * len(header))
    for directory in targets:
        output, seconds = run_one(directory)
        row = summarise(output, seconds)
        results.append(row)
        print(f"{directory.parent.name + '/' + directory.name:<34}"
              f"{row['verified']:>4}{row['attestation_discrepancy']:>4}"
              f"{row['reconstructed']:>4}{row['ambiguous']:>5}"
              f"{row['unresolved']:>5}{row['mean_candidate_set_size']:>9.2f}"
              f"{row['max_candidate_set_size']:>7}{row['rows_assigned']:>7}"
              f"{row['seconds']:>7.1f}")
    total = lambda key: sum(r[key] for r in results)
    print("-" * len(header))
    print(f"{'TOTAL':<34}{total('verified'):>4}"
          f"{total('attestation_discrepancy'):>4}{total('reconstructed'):>4}"
          f"{total('ambiguous'):>5}{total('unresolved'):>5}"
          f"{'':>9}{max((r['max_candidate_set_size'] for r in results), default=0):>7}"
          f"{total('rows_assigned'):>7}{total('seconds'):>7.1f}")
    if arguments.json:
        arguments.json.write_text(json.dumps(results, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
