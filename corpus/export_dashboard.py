"""dashboard/data.json -- the ONE file the dashboard UI is allowed to read.

    python3 corpus/export_dashboard.py

## Why an export layer, and not the raw artefacts directly

Reading raw artefacts from a UI spreads number-derivation across two
codebases, which is exactly how a figure ends up computed one way by the
script that owns it and a slightly different way by the thing displaying it
-- the drift class `DECISIONS.md` sec 44.4 catalogues four instances of
already. This module is the one place that derivation happens for anything
the dashboard shows; the dashboard reads `dashboard/data.json` and nothing
else. `DASHBOARD_DATA.md` documents, for every field in this file, which
module owns it and what its denominator and scope are.

## What this module does NOT do

It computes nothing the repository does not already compute. Every number
below is READ from the function or file that owns it:

    corpus.claims_ledger.rows()      the CLAIMS.md schema itself, reused
    corpus.coverage.split()          the three-way coverage split
    corpus.three_systems.*_row()     the per-dataset three-system comparison
    corpus.scorecard.D15             the held D15 measurement (an
                                      already-committed constant, not
                                      re-derived -- see that module's own
                                      comment on why)
    corpus/oracle_results.json       the resolver, per dataset, unmodified
    corpus/baseline_results.json     the frozen cascade, per dataset,
                                      unmodified
    `git log`                        the commit-ordering evidence, live

If a figure the dashboard would want is not owned anywhere, it is NOT
invented here -- it is listed in `not_available` with a reason, and
`DASHBOARD_DATA.md` records the screen it would have fed as honestly
incomplete.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus import coverage as coverage_mod              # noqa: E402
from corpus import claims_ledger                          # noqa: E402
from corpus import three_systems                          # noqa: E402
from corpus.scorecard import D15                          # noqa: E402


def load(name: str):
    path = ROOT / "corpus" / name
    return json.loads(path.read_text()) if path.exists() else None


def build_claims() -> list[dict]:
    """The CLAIMS.md ledger, verbatim -- already has value/denom/scope/artefact."""
    return claims_ledger.rows()


def build_coverage(oracle: list[dict]) -> dict:
    """The four coverage scopes, from the one function that owns the split.

    `split()` already returns `scope`/`scope_label` -- passed through
    unmodified, not re-added.
    """
    return {scope: coverage_mod.split(oracle, scope)
            for scope in coverage_mod.SCOPES}


def build_three_systems() -> dict:
    """Per-dataset naive/frozen/resolver rows, via the functions that already
    build `THREE_SYSTEMS.md` -- not a re-parse of that markdown file.
    """
    frozen_path = ROOT / "corpus" / "baseline_results.json"
    resolver_path = ROOT / "corpus" / "oracle_results.json"
    frozen: dict[str, dict] = {}
    if frozen_path.exists():
        for entry in json.loads(frozen_path.read_text()):
            frozen[f"{entry.get('family', 'datasets')}/{entry['dataset']}"] = entry
    resolver: dict[str, dict] = {}
    if resolver_path.exists():
        for entry in json.loads(resolver_path.read_text()):
            resolver[entry["dataset"]] = entry

    rows = []
    for directory in three_systems.dataset_dirs():
        key = f"{directory.parent.name}/{directory.name}"
        rows.append({
            "dataset": key, "family": directory.parent.name,
            "lines": three_systems.our_lines(directory),
            "naive": three_systems.naive_row(directory),
            "frozen": three_systems.frozen_row(frozen.get(key)),
            "resolver": three_systems.resolver_row(resolver.get(key)),
        })
    return {"per_dataset": rows, "source": "corpus/THREE_SYSTEMS.md's own "
            "row-building functions, reused directly"}


def verify_hashes() -> dict:
    """Runs the exact documented verification commands and reports pass/fail.

    Not a re-implementation of hash checking -- `shasum` itself, via
    subprocess, exactly as README.md documents. A live check, not a cached
    claim.
    """
    primary = subprocess.run(
        ["bash", "-c",
         "shasum -a 256 -c <(sed 's|^\\([0-9a-f]*\\) |\\1  |' "
         "engine/DATASET_HASHES.txt)"],
        cwd=ROOT, capture_output=True, text=True)
    corpus_ok, corpus_total = 0, 0
    for manifest in sorted(ROOT.glob("corpus/datasets*/*/DATASET_HASHES.txt")):
        corpus_total += 1
        result = subprocess.run(["shasum", "-a", "256", "-c",
                                  "DATASET_HASHES.txt"],
                                 cwd=manifest.parent, capture_output=True,
                                 text=True)
        if result.returncode == 0:
            corpus_ok += 1
    return {
        "primary_dataset": {"passed": primary.returncode == 0,
                             "detail": primary.stdout.strip().splitlines()},
        "corpus_datasets": {"passed": corpus_ok, "of": corpus_total},
    }


def build_commit_ordering() -> dict:
    """The provenance chain, read live from `git log` -- not a static list.

    Matches the ordering argument in README.md/CHECKPOINT.md: this reads the
    actual repository history rather than repeating a claim about it.
    """
    result = subprocess.run(
        ["git", "log", "--reverse", "--format=%H|%ai|%s"],
        cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return {"available": False, "reason": "git log failed"}
    commits = []
    for line in result.stdout.strip().splitlines():
        sha, date, subject = line.split("|", 2)
        commits.append({"sha": sha[:10], "date": date, "subject": subject})
    return {"available": True, "count": len(commits),
            "first_ten": commits[:10], "last_ten": commits[-10:]}


def build_self_correction_record() -> dict:
    """DECISIONS.md sec 44.4's count of self-caught errors.

    NOT computed here -- there is no script that owns "how many times has
    this project found the error it had just catalogued", because counting
    that requires reading prose, not data. Per this module's own rule
    (compute nothing uncomputed elsewhere; report what is missing rather than
    inventing it), this is a citation, not a figure: the dashboard's
    Integrity screen must render it as a link to `DECISIONS.md` sec 44.4, not
    as a number this export asserts.
    """
    return {"available_as_number": False,
            "reason": "counting instances of a narrative pattern is not a "
                      "quantity any script owns; §44.4 is prose, correctly",
            "citation": "DECISIONS.md §44.4"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path,
                        default=ROOT / "dashboard" / "data.json")
    parser.add_argument("--skip-hashes", action="store_true",
                        help="skip the live shasum verification (slow-ish, "
                             "~1s; skip only for a smoke run)")
    arguments = parser.parse_args()

    oracle = load("oracle_results.json") or []
    baseline = load("baseline_results.json") or []

    not_available = []
    if not oracle:
        not_available.append({"field": "coverage, three_systems.resolver, "
                              "claims", "reason": "corpus/oracle_results.json "
                              "does not exist -- run "
                              "`corpus/score_resolver.py --all` first"})
    if not baseline:
        not_available.append({"field": "three_systems.frozen",
                              "reason": "corpus/baseline_results.json does "
                              "not exist -- run "
                              "`corpus/baseline_old_engine.py --all` first"})

    export = {
        "generated_by": "corpus/export_dashboard.py",
        "note": "Every field below is read from the module or file that "
                "owns it; this script computes nothing new. See "
                "DASHBOARD_DATA.md for the source of each field.",
        "claims": build_claims(),
        "coverage": build_coverage(oracle) if oracle else None,
        "three_systems": build_three_systems(),
        "d15": {**D15, "source": "corpus/scorecard.py's D15 constant -- a "
                "committed measurement (investigation/D15_MEASUREMENT.md), "
                "held as data rather than re-derived on every export"},
        "hashes": None if arguments.skip_hashes else verify_hashes(),
        "commit_ordering": build_commit_ordering(),
        "self_correction_record": build_self_correction_record(),
        "not_available": not_available,
    }

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(export, indent=1) + "\n")
    print(f"wrote {arguments.out}")
    if not_available:
        print(f"{len(not_available)} field group(s) not available -- see "
              "not_available in the output", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
