"""Same seed -> byte-identical output. SETTLEMENT_SPEC.md sec 7."""

import hashlib
import shutil
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

import generator  # noqa: E402

DATA_FILES = ["recon_combined.json", "disputes.json", "bank_statement.csv",
              "erp_orders.csv", "gstr2b.csv"]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_three_runs_are_byte_identical(tmp_path):
    digests = []
    for run in range(3):
        out, truth = tmp_path / f"d{run}", tmp_path / f"t{run}"
        generator.generate(20260822, out, truth)
        digests.append({f: _digest(out / f) for f in DATA_FILES}
                       | {"ground_truth.json": _digest(truth / "ground_truth.json")})
    assert digests[0] == digests[1] == digests[2], "generator is not deterministic"


def test_frozen_dataset_matches_a_fresh_run(tmp_path):
    """The committed data IS what the committed generator produces."""
    out, truth = tmp_path / "d", tmp_path / "t"
    generator.generate(20260822, out, truth)
    for name in DATA_FILES:
        assert _digest(out / name) == _digest(generator.ROOT / "data" / name), name
    assert _digest(truth / "ground_truth.json") == _digest(
        generator.ROOT / "ground_truth" / "ground_truth.json")


def test_hashes_file_matches_the_frozen_data():
    lines = (generator.ROOT / "DATASET_HASHES.txt").read_text().splitlines()
    entries = [ln.split() for ln in lines if ln and not ln.startswith("#")]
    assert entries, "DATASET_HASHES.txt has no entries"
    for digest, relpath in entries:
        target = generator.ROOT.parent / relpath
        assert target.exists(), relpath
        assert _digest(target) == digest, f"{relpath} does not match its frozen hash"


def test_a_different_seed_produces_different_data(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generator.generate(20260822, a, tmp_path / "ta")
    generator.generate(11111111, b, tmp_path / "tb")
    assert _digest(a / "recon_combined.json") != _digest(b / "recon_combined.json")
