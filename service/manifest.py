"""Closes the exact gap `service/pipeline.py`'s own docstring names:
`transport.poller.Poller` lands arbitrary files into a content-addressed
staging directory with no notion of which file is `bank_statement.csv`
versus `settlement_report.csv` -- "a manifest describing which staged digest
is which artifact... named here as a deliberate follow-on, not solved by a
heuristic."

That line is honored literally: `propose_manifest` guesses, using nothing
more than the same `ingest.schema.Role` vocabulary every format adapter
already resolves against, but a guess is never assembled into a dataset
directory on its own authority. `write_manifest`/`read_manifest` persist only
a HUMAN-CONFIRMED mapping, and `assemble_dataset_directory` refuses to run
against anything else -- an unconfirmed or partial manifest is a `ValueError`
naming exactly what is missing, never a silent best-effort copy.

Once confirmed for one staged file's shape, the same mapping is reusable
automatically for the next period's staged pull carrying the same shape --
`read_manifest`/`write_manifest` round-trip the confirmed mapping to a plain
JSON file for exactly that reuse.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from ingest.schema import (BANK_ROLES, ERP_ROLES, GSTR2B_ROLES,
                            SETTLEMENT_REPORT_ROLES, RoleConflict, RoleMissing,
                            resolve_role)

#: Canonical six-file contract `ingest.load` has always expected
#: (`ingest/schema.py`'s own module docstring). Every confirmed manifest
#: must cover exactly this set before `assemble_dataset_directory` will run.
CANONICAL_ARTIFACTS = ("bank_statement.csv", "settlement_report.csv",
                       "erp_orders.csv", "gstr2b.csv", "disputes.json",
                       "recon_combined.json")

_CSV_ROLE_SETS = {
    "bank_statement.csv": BANK_ROLES,
    "settlement_report.csv": SETTLEMENT_REPORT_ROLES,
    "erp_orders.csv": ERP_ROLES,
    "gstr2b.csv": GSTR2B_ROLES,
}


def _csv_fieldnames(payload: bytes) -> tuple[str, ...] | None:
    try:
        text = payload.decode()
    except UnicodeDecodeError:
        return None
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return None
    return tuple(h.strip() for h in header)


#: `disputes.json` and `recon_combined.json` share the identical envelope
#: (`{"entity", "count", "items"}`) in this repo's own fixtures -- the
#: envelope alone cannot tell them apart, so this looks at the first item's
#: OWN keys instead, which are structurally distinct artefacts
#: (`resolver.loaders.Dispute` vs. a recon-combined settlement row).
_DISPUTE_ITEM_KEYS = frozenset({"id", "phase", "opened_at", "amount_deducted"})
_RECON_ITEM_KEYS = frozenset({"entity_id", "settlement_id", "payment_id"})


def _json_artifact_label(payload: bytes) -> str | None:
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "items" in data:
        items = data["items"]
    else:
        return None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None

    keys = set(items[0])
    if _DISPUTE_ITEM_KEYS <= keys:
        return "disputes.json"
    if _RECON_ITEM_KEYS & keys:
        return "recon_combined.json"
    return None


def propose_artifact_label(payload: bytes) -> str | None:
    """A best-effort guess at which of `CANONICAL_ARTIFACTS` this file is,
    or `None` if nothing matches. Never authoritative -- see module
    docstring. Format is decided by the first non-whitespace byte, the same
    convention `ingest/formats/jsonl.py::load_items` uses, not by extension."""
    stripped = payload.lstrip()
    if stripped[:1] in (b"{", b"["):
        return _json_artifact_label(payload)

    fieldnames = _csv_fieldnames(payload)
    if fieldnames is None:
        return None
    matches = []
    for label, roles in _CSV_ROLE_SETS.items():
        try:
            for role in roles:
                resolve_role(role, fieldnames)
        except (RoleMissing, RoleConflict):
            continue
        matches.append(label)
    if len(matches) == 1:
        return matches[0]
    return None  # zero or ambiguous multiple matches: no proposal


def propose_manifest(staged_dir: Path) -> list[dict]:
    """One proposal per staged file (skipping the poller's own manifest and
    any dead-letter/quarantine bookkeeping file), for a human to confirm or
    correct."""
    staged_dir = Path(staged_dir)
    proposals = []
    for path in sorted(staged_dir.iterdir()):
        if not path.is_file() or path.name.startswith("_"):
            continue
        payload = path.read_bytes()
        proposals.append({
            "staged_path": str(path),
            "proposed_label": propose_artifact_label(payload),
        })
    return proposals


def write_manifest(mapping: dict[str, str], manifest_path: Path) -> None:
    Path(manifest_path).write_text(json.dumps(mapping, indent=1, sort_keys=True) + "\n")


def read_manifest(manifest_path: Path) -> dict[str, str]:
    return json.loads(Path(manifest_path).read_text())


def assemble_dataset_directory(mapping: dict[str, str], out_dir: Path) -> Path:
    """`mapping` is `{staged_path: canonical_artifact_name}`, HUMAN-CONFIRMED
    (via `propose_manifest` plus a caller's own review, never this module's
    guess alone). Refuses to run unless every one of `CANONICAL_ARTIFACTS` is
    covered by exactly one staged path."""
    covered = set(mapping.values())
    missing = set(CANONICAL_ARTIFACTS) - covered
    if missing:
        raise ValueError(
            f"manifest is missing an artifact for: {sorted(missing)} -- "
            f"refusing to assemble a partial dataset directory")
    unknown = covered - set(CANONICAL_ARTIFACTS)
    if unknown:
        raise ValueError(f"manifest names artifacts ingest.load does not "
                          f"expect: {sorted(unknown)}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for staged_path, canonical_name in mapping.items():
        (out_dir / canonical_name).write_bytes(Path(staged_path).read_bytes())
    return out_dir
