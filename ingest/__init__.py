"""Multi-format ingestion, layered strictly downstream of `resolver/`.

`resolver/tests/test_isolation.py` forbids every resolver module except
`loaders.py` from touching a file, and its live-import-graph test imports
every resolver module and diffs `sys.modules` -- so this package must never
be imported BY `resolver/`. The reverse is fine: `ingest/formats/csv_json.py`
imports `resolver.loaders` for its dataclasses and `paise`, and
`ingest/tests/test_conformance.py` proves the two readers agree on all 45
dataset directories in the repo.

Nothing here reads `ground_truth.json`; `resolver.loaders.FORBIDDEN` and
`GroundTruthAccess` are inherited unchanged (`ingest/formats/csv_json.py`
checks the same guard before opening anything).
"""

from __future__ import annotations

from pathlib import Path

from ingest.formats import csv_json
from resolver.loaders import Dataset


def load(directory: Path, *, fmt: str = "auto") -> Dataset:
    """`directory` -> `Dataset`, format-detected unless `fmt` is given.

    Phase A1: `fmt="auto"` and `fmt="csv_json"` both go through
    `ingest.formats.csv_json.load` -- an independent second implementation of
    the six-file contract, built on the role vocabulary in `ingest/schema.py`
    rather than on `resolver.loaders`'s hardcoded column lookups. Later phases
    add `fmt="xlsx"`, `fmt="camt053"`, `fmt="mt940"` converging through the
    same `ingest/normalize.py` builders.
    """
    if fmt in ("auto", "csv_json"):
        return csv_json.load(directory)
    raise ValueError(f"unknown format: {fmt!r}")
