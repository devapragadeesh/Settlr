"""`ingest.load` must equal `resolver.loaders.load`, on every dataset on disk.

Modelled on `corpus/tests/test_conformance.py`, which holds
`corpus/generator/sim.py` to the same standard against the frozen simulator.
This is Phase A0 of `DECISIONS.md` Sec.79: before any new format is added, the
new reader and the old one must be provably in lock-step on the two schema
families that already exist (`utr,date` frozen-engine spelling and
`bank_reference,value_date` corpus spelling -- Sec.72).

Ground truth is not touched: this test loads `ground_truth.json` for NOTHING,
compares only what both loaders return from the frozen `resolver.loaders`
public dataclasses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import ingest
from resolver.loaders import load as resolver_load

ROOT = Path(__file__).resolve().parent.parent.parent


def _dataset_dirs() -> list[Path]:
    dirs = [ROOT / "engine" / "data", ROOT / "holdout" / "data"]
    dirs += sorted((ROOT / "scale").glob("data_*"))
    for family in ("datasets", "datasets_v2", "datasets_gst",
                    "datasets_gst_holdout", "datasets_bankside"):
        base = ROOT / "corpus" / family
        if base.exists():
            dirs += sorted(p for p in base.iterdir() if p.is_dir())
    return dirs


DATASET_DIRS = _dataset_dirs()


@pytest.mark.parametrize("directory", DATASET_DIRS, ids=lambda d: str(d.relative_to(ROOT)))
def test_ingest_matches_resolver_loaders(directory: Path) -> None:
    want = resolver_load(directory)
    got = ingest.load(directory)

    assert got.name == want.name
    assert got.rows == want.rows
    assert got.bank == want.bank
    assert got.settlement_report == want.settlement_report
    assert got.erp_order_ids == want.erp_order_ids
    assert got.disputes == want.disputes
    assert got.gstr2b == want.gstr2b


def test_exactly_45_dataset_directories_were_found() -> None:
    # A change in this count is itself a finding -- it means a dataset family
    # was added or removed since this test was written, and the fixed number
    # is the anti-vacuity guard against the parametrize list silently going
    # empty.
    assert len(DATASET_DIRS) == 45
