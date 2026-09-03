"""Multi-format ingestion, layered strictly downstream of `resolver/`.

`resolver/tests/test_isolation.py` forbids every resolver module except
`loaders.py` from touching a file, and its live-import-graph test imports
every resolver module and diffs `sys.modules` -- so this package must never
be imported BY `resolver/`. The reverse is fine and is how Phase A0 works:
`ingest.load` currently delegates to `resolver.loaders.load` so the two stay
provably in lock-step (`ingest/tests/test_conformance.py`) before any new
format is added.

Nothing here reads `ground_truth.json`; `resolver.loaders.FORBIDDEN` and
`GroundTruthAccess` are inherited unchanged through the delegation.
"""

from __future__ import annotations

from pathlib import Path

from resolver.loaders import Dataset, load as _resolver_load


def load(directory: Path, *, fmt: str = "auto") -> Dataset:
    """`directory` -> `Dataset`, format-detected unless `fmt` is given.

    Phase A0: `fmt="auto"` and `fmt="csv_json"` both delegate to
    `resolver.loaders.load` unchanged. Later phases add `fmt="xlsx"`,
    `fmt="camt053"`, `fmt="mt940"` without touching this branch's behaviour --
    the conformance test in `ingest/tests/test_conformance.py` is the proof
    that this delegation is exact, not approximate.
    """
    if fmt in ("auto", "csv_json"):
        return _resolver_load(directory)
    raise ValueError(f"unknown format: {fmt!r}")
