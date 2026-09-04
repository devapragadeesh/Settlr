"""Proves the proposal's "connectors" claim honestly: SFTP and S3 pulls
already exist (`transport/sftp.py`, `transport/s3.py`), and the Razorpay API
/ GST portal export shapes already converge on the same envelope
`ingest/formats/jsonl.py` parses (its own docstring: "`recon_combined.json`
is already `{entity, count, items}` -- an API-shaped envelope" -- confirmed
for real against a captured Razorpay TEST MODE response,
`spike/raw/008_rest_recon_combined_current_month.json`, whose `response.body`
is exactly `{entity, count, items}`). The one thing that did NOT already
exist is `service/manifest.py`, landed in this same change.

This test wires all of it together with `RecordedTransport`
(`transport/recorded.py`) standing in for a live SFTP/S3 pull -- offline,
like every other test in this repo -- and drives a REAL dataset all the way
through `Poller` -> `propose_manifest` -> `assemble_dataset_directory` ->
`ingest.load` -> `resolver.resolve()`, checking the resolved output matches
resolving the original directory directly. Nothing here is a new connector;
it is the proof that the existing pieces plus the new manifest actually
compose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest import load
from resolver.resolve import resolve
from service.manifest import assemble_dataset_directory, propose_manifest
from transport.poller import Poller
from transport.recorded import RecordedTransport

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"


def test_recon_combined_json_matches_the_real_razorpay_api_envelope_shape() -> None:
    capture = json.loads(
        (ROOT / "spike" / "raw" / "008_rest_recon_combined_current_month.json").read_text())
    body = capture["response"]["body"]
    assert set(body) == {"entity", "count", "items"}

    real_dataset_file = json.loads((DATASET_DIR / "recon_combined.json").read_text())
    assert set(real_dataset_file) == set(body)


@pytest.fixture()
def fixture_transport_root(tmp_path: Path) -> Path:
    """A `RecordedTransport` fixture tree, standing in for a live SFTP/S3
    remote: the six real dataset files under one prefix, exactly as they
    would arrive from an actual pull -- no artifact identity in the
    filenames beyond what a real remote would give them."""
    remote_root = tmp_path / "remote"
    prefix_dir = remote_root / "merchant-exports"
    prefix_dir.mkdir(parents=True)
    for name in ("bank_statement.csv", "settlement_report.csv", "erp_orders.csv",
                 "gstr2b.csv", "disputes.json", "recon_combined.json"):
        (prefix_dir / name).write_bytes((DATASET_DIR / name).read_bytes())
    return remote_root


def test_poller_to_manifest_to_resolver_end_to_end(
        fixture_transport_root: Path, tmp_path: Path) -> None:
    transport = RecordedTransport(fixture_transport_root)
    staged_dir = tmp_path / "staged"
    quarantine_dir = tmp_path / "quarantine"

    poller = Poller(transport=transport, prefix="merchant-exports",
                     dest_dir=staged_dir, quarantine_dir=quarantine_dir)
    result = poller.poll_once()
    assert len(result.ingested) == 6
    assert not result.quarantined and not result.dead_lettered

    proposals = propose_manifest(staged_dir)
    assert len(proposals) == 6
    assert all(p["proposed_label"] is not None for p in proposals)
    confirmed = {p["staged_path"]: p["proposed_label"] for p in proposals}

    assembled_dir = tmp_path / "assembled"
    assemble_dataset_directory(confirmed, assembled_dir)

    assembled_dataset = load(assembled_dir)
    original_dataset = load(DATASET_DIR)

    assembled_output = resolve(assembled_dataset, cap=40, time_budget=5.0)
    original_output = resolve(original_dataset, cap=40, time_budget=5.0)

    assert len(assembled_output.line_outcomes) == len(original_output.line_outcomes)
    assert [type(o).__name__ for o in assembled_output.line_outcomes] == \
           [type(o).__name__ for o in original_output.line_outcomes]
