"""Proves the manifest module closes `service/pipeline.py`'s named gap for
real: copy one real dataset's six files into a directory named the way
`transport.poller.Poller` actually names accepted files (content-digest
prefix, no notion of which file is which), propose a manifest, confirm it,
assemble a canonical directory, and check `ingest.load` on the assembled
directory produces the IDENTICAL `Dataset` as loading the original directory
directly -- not just "doesn't crash".
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ingest import load
from service.manifest import (CANONICAL_ARTIFACTS, assemble_dataset_directory,
                               propose_artifact_label, propose_manifest,
                               read_manifest, write_manifest)

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"


@pytest.fixture()
def staged_dir(tmp_path: Path) -> Path:
    """Mirrors `transport.poller.Poller`'s own naming:
    `dest_dir/<sha256>_<basename>` -- so the staged filenames carry no
    artifact identity at all, exactly the situation the manifest exists for.
    """
    staged = tmp_path / "staged"
    staged.mkdir()
    for name in ("bank_statement.csv", "settlement_report.csv", "erp_orders.csv",
                 "gstr2b.csv", "disputes.json", "recon_combined.json"):
        payload = (DATASET_DIR / name).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()[:16]
        (staged / f"{digest}_{name}").write_bytes(payload)
    return staged


def test_every_staged_file_gets_the_correct_unambiguous_proposal(staged_dir: Path) -> None:
    proposals = propose_manifest(staged_dir)
    assert len(proposals) == 6

    proposed_labels = {Path(p["staged_path"]).name.split("_", 1)[1]: p["proposed_label"]
                        for p in proposals}
    for original_name in ("bank_statement.csv", "settlement_report.csv",
                          "erp_orders.csv", "gstr2b.csv", "disputes.json",
                          "recon_combined.json"):
        assert proposed_labels[original_name] == original_name


def test_manifest_round_trip_produces_an_identical_dataset(
        staged_dir: Path, tmp_path: Path) -> None:
    proposals = propose_manifest(staged_dir)
    confirmed = {p["staged_path"]: p["proposed_label"] for p in proposals}

    manifest_path = tmp_path / "manifest.json"
    write_manifest(confirmed, manifest_path)
    reloaded = read_manifest(manifest_path)

    out_dir = tmp_path / "assembled"
    assemble_dataset_directory(reloaded, out_dir)

    original = load(DATASET_DIR)
    assembled = load(out_dir)
    # `Dataset.name` is the directory's own name, not part of its content --
    # everything else must be byte-for-byte identical to the original load.
    from dataclasses import replace
    assert replace(assembled, name=original.name) == original


def test_assembly_refuses_a_manifest_missing_an_artifact(
        staged_dir: Path, tmp_path: Path) -> None:
    proposals = propose_manifest(staged_dir)
    confirmed = {p["staged_path"]: p["proposed_label"] for p in proposals}
    confirmed.pop(next(iter(confirmed)))  # drop one entry

    with pytest.raises(ValueError, match="missing"):
        assemble_dataset_directory(confirmed, tmp_path / "assembled")


def test_assembly_refuses_an_unknown_artifact_name(staged_dir: Path, tmp_path: Path) -> None:
    (staged_dir / "x").write_bytes(b"a,b\n1,2\n")
    bad_mapping = {str(staged_dir / "x"): "not_a_real_artifact.csv"}
    for name in CANONICAL_ARTIFACTS:
        bad_mapping[str(DATASET_DIR / name)] = name

    with pytest.raises(ValueError, match="does not expect"):
        assemble_dataset_directory(bad_mapping, tmp_path / "assembled")


def test_an_ambiguous_or_unrecognised_file_gets_no_proposal(tmp_path: Path) -> None:
    assert propose_artifact_label(b"not,a,known,shape\n1,2,3,4\n") is None
    assert propose_artifact_label(b"just plain text, not even csv") is None
