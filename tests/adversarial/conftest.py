"""Fixtures for the adversarial / malformed-input suite.

`resolver/` and `matching/` are exercised **read only** here: `load()` and the
resolve/cascade entry point, never anything that writes into either package
or monkeypatches its internals. See `DECISIONS.md` 52 for the governing
decision and the three-bucket rubric this whole directory implements.

One minimal, valid dataset is built once per session from the smallest
existing corpus axis point on disk, `corpus/datasets/A10_B100_Cmax` (20 bank
lines -- see `python3 -m corpus.generator.build --list`). This directory is
frozen/tracked and is never written to; every fixture here works on a *copy*
in a pytest tmp dir.

Two baseline shapes exist because the two packages read different bank-column
names:

* `resolver_baseline` -- the corpus dataset's own five files, verbatim
  (`recon_combined.json`, `bank_statement.csv` with `bank_reference` /
  `value_date`, `settlement_report.csv`, `erp_orders.csv`, `disputes.json`).
  `ground_truth.json`, `DATASET_HASHES.txt` and `GENERATION_REPORT.md` are
  never copied -- this suite has no business opening the answer key either.
* `matching_baseline` -- the same dataset with the bank file's columns
  renamed to `utr` / `date`, exactly the projection
  `corpus/baseline_old_engine.py` already uses to run the frozen cascade over
  a corpus dataset. `settlement_report.csv` is omitted because
  `matching/loaders.py` never reads it -- the frozen cascade gets its
  composition claim from `settlement_utr` on the recon rows instead.

Every test case is produced by `cases.py`: a mutation that clones one of
these baselines into a fresh tmp dir and corrupts exactly one field or file.
"""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT,):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

CORPUS_SOURCE = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"

#: Files copied verbatim into the resolver-shaped baseline.
RESOLVER_FILES = ("recon_combined.json", "bank_statement.csv",
                   "settlement_report.csv", "erp_orders.csv", "disputes.json")

#: Files copied verbatim (unrenamed) into the matching-shaped baseline.
MATCHING_COPIED_FILES = ("recon_combined.json", "erp_orders.csv",
                          "gstr2b.csv", "disputes.json")


def _project_bank_statement(source: Path, dest: Path) -> None:
    """`bank_reference,value_date,...` -> `utr,date,...`. Renaming only; every
    line is kept, exactly as `corpus/baseline_old_engine.py.project` does."""
    with source.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    with dest.open("w", newline="\n") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["utr", "date", "narration", "amount"],
            lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "utr": row["bank_reference"], "date": row["value_date"],
                "narration": row["narration"], "amount": row["amount"]})


def build_resolver_baseline(dest: Path) -> Path:
    """Pure function behind the `resolver_baseline` fixture, factored out so
    `run_adversarial.py` (no pytest involved) can build the same baseline."""
    assert CORPUS_SOURCE.exists(), (
        f"expected frozen corpus dataset at {CORPUS_SOURCE}; run "
        "`python3 -m corpus.generator.build --list` to confirm it is still "
        "the smallest pool_target axis point")
    dest.mkdir(parents=True, exist_ok=True)
    for name in RESOLVER_FILES:
        source = CORPUS_SOURCE / name
        if source.exists():
            shutil.copy(source, dest / name)
    return dest


def build_matching_baseline(dest: Path) -> Path:
    """Pure function behind the `matching_baseline` fixture; see
    `build_resolver_baseline`."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in MATCHING_COPIED_FILES:
        source = CORPUS_SOURCE / name
        if source.exists():
            shutil.copy(source, dest / name)
    _project_bank_statement(CORPUS_SOURCE / "bank_statement.csv",
                            dest / "bank_statement.csv")
    return dest


@pytest.fixture(scope="session")
def resolver_baseline(tmp_path_factory) -> Path:
    return build_resolver_baseline(tmp_path_factory.mktemp("resolver_base") / "dataset")


@pytest.fixture(scope="session")
def matching_baseline(tmp_path_factory) -> Path:
    return build_matching_baseline(tmp_path_factory.mktemp("matching_base") / "dataset")


def clone_dataset(baseline: Path, tmp_path: Path) -> Path:
    """Copy a baseline into a fresh directory the caller may corrupt."""
    dest = tmp_path / "dataset"
    shutil.copytree(baseline, dest)
    return dest


@pytest.fixture
def resolver_case_dir(resolver_baseline, tmp_path) -> Path:
    return clone_dataset(resolver_baseline, tmp_path)


@pytest.fixture
def matching_case_dir(matching_baseline, tmp_path) -> Path:
    return clone_dataset(matching_baseline, tmp_path)
