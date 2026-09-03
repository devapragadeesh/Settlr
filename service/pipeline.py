"""The `ingest -> resolve -> persist` chain, each step already idempotent on
its own (Sec.80's role-based reader, Sec.86's `run_id` derivation), composed
into one call.

**Deliberately does not include the "pull" step.** `transport.poller.Poller`
(Phase B2) lands arbitrary files into a content-addressed staging directory,
one file at a time -- it has no notion of which uploaded file is
`bank_statement.csv` versus `settlement_report.csv` for a given dataset,
because that association is not present in the file's bytes and guessing it
would be exactly the kind of invented structure `CLAUDE.md`'s D5 rule warns
against (applied here to file identity rather than data). Wiring a poller's
staging output into a canonical six-file dataset directory is a real,
separate integration decision -- a manifest describing which staged digest
is which artifact -- and is named here as a deliberate follow-on, not solved
by a heuristic. `run_pipeline` therefore takes an already-materialised
dataset directory (the same six-file contract `ingest.load` has always
expected), which is what a poller's output would need to be assembled into
before this function runs.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from ingest import load
from resolver.resolve import resolve
from store.writer import write_run

ROOT = Path(__file__).resolve().parent.parent

#: Source files whose content defines "the same code" for `code_digest`.
#: Only `resolver/` and `resolver_contract/` -- what `ingest/`, `transport/`
#: or `store/` do to get a `Dataset` onto disk does not change what the
#: resolver DECIDES about it, so it is deliberately excluded from this
#: digest.
_CODE_ROOTS = ("resolver", "resolver_contract")

#: The six-file contract `ingest.load`/`resolver.loaders.load` already read.
_ARTIFACT_NAMES = ("recon_combined.json", "bank_statement.csv",
                    "settlement_report.csv", "erp_orders.csv",
                    "disputes.json", "gstr2b.csv")


def code_digest(root: Path = ROOT) -> str:
    hasher = hashlib.sha256()
    for name in _CODE_ROOTS:
        for path in sorted((root / name).rglob("*.py")):
            hasher.update(str(path.relative_to(root)).encode())
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


def input_digest(dataset_dir: Path) -> str:
    hasher = hashlib.sha256()
    for name in _ARTIFACT_NAMES:
        path = dataset_dir / name
        if not path.exists():
            continue
        hasher.update(name.encode())
        hasher.update(hashlib.sha256(path.read_bytes()).digest())
    return hasher.hexdigest()


def run_pipeline(dataset_dir: Path, conn: sqlite3.Connection, *,
                  cap: int = 200, time_budget: float = 10.0) -> str:
    dataset_dir = Path(dataset_dir)
    dataset = load(dataset_dir)

    started_at = datetime.now(timezone.utc).isoformat()
    clock_start = time.perf_counter()
    output = resolve(dataset, cap=cap, time_budget=time_budget)
    seconds = time.perf_counter() - clock_start
    finished_at = datetime.now(timezone.utc).isoformat()

    all_row_ids = frozenset(row["entity_id"] for row in dataset.rows)

    sources = []
    for name in _ARTIFACT_NAMES:
        path = dataset_dir / name
        if not path.exists():
            continue
        sources.append(dict(
            artifact_path=name, source_system="unknown", format=path.suffix.lstrip("."),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            fetched_at=None, transport="local"))

    return write_run(conn, output, all_row_ids=all_row_ids, cap=cap,
                      time_budget=time_budget,
                      input_digest=input_digest(dataset_dir),
                      code_digest=code_digest(), started_at=started_at,
                      finished_at=finished_at, seconds=seconds,
                      sources=sources)
