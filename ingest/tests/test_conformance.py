"""`ingest.load` must equal `resolver.loaders.load`, on every dataset on disk.

Modelled on `corpus/tests/test_conformance.py`, which holds
`corpus/generator/sim.py` to the same standard against the frozen simulator.
Phase A0 (`DECISIONS.md` Sec.79) proved this as a straight delegation. Phase
A1 (Sec.80) rebuilt `ingest.load`'s CSV/JSON path as an independent second
reader on the role vocabulary in `ingest/schema.py`, so this test is now a
convergence proof between two separately-written implementations of the same
six-file contract on the two schema families that exist (`utr,date`
frozen-engine spelling and `bank_reference,value_date` corpus spelling --
Sec.72), not a tautology about a wrapper agreeing with what it wraps.

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
    #
    # scale/data_* (8 dirs) is gitignored by design (scale/README.md,
    # .gitignore: "large and fully reproducible from generate_scale.py...
    # not committed", ~30 min to regenerate) -- so a clean CI checkout has
    # 37, not 45, until that script has been run. This asserts the number
    # that is actually guaranteed by what git tracks, and the full 45 when
    # a local dev has generated the scale fixtures, rather than asserting a
    # number CI can never satisfy from a checkout alone.
    scale_present = (ROOT / "scale" / "data_250").exists()
    assert len(DATASET_DIRS) == (45 if scale_present else 37)
