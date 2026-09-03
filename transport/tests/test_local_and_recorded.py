"""`LocalTransport` and `RecordedTransport` -- entirely offline, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transport.base import PullRecord
from transport.local import LocalTransport
from transport.recorded import MANIFEST_NAME, RecordedTransport, record_fixtures


def _make_tree(root: Path) -> None:
    (root / "incoming").mkdir(parents=True)
    (root / "incoming" / "a.csv").write_text("a,b\n1,2\n")
    (root / "incoming" / "sub").mkdir()
    (root / "incoming" / "sub" / "b.csv").write_text("c,d\n3,4\n")


def test_local_transport_lists_and_fetches(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    transport = LocalTransport(tmp_path)

    files = {f.key for f in transport.list("incoming")}
    assert files == {"incoming/a.csv", "incoming/sub/b.csv"}
    assert transport.fetch("incoming/a.csv") == b"a,b\n1,2\n"


def test_local_transport_list_on_missing_prefix_is_empty(tmp_path: Path) -> None:
    transport = LocalTransport(tmp_path)
    assert transport.list("nowhere") == []


def test_local_transport_fetch_on_missing_key_raises(tmp_path: Path) -> None:
    transport = LocalTransport(tmp_path)
    with pytest.raises(FileNotFoundError):
        transport.fetch("nowhere.csv")


def test_record_fixtures_captures_a_redacted_manifest(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _make_tree(source_root)
    source = LocalTransport(source_root)

    out_dir = tmp_path / "fixtures"
    records = record_fixtures(source, "incoming", out_dir, endpoint="test-endpoint")

    assert len(records) == 2
    for record in records:
        assert isinstance(record, PullRecord)
        assert record.outcome == "ok"
        assert record.endpoint == "test-endpoint"
        # The evidence trail never carries a credential or the payload --
        # only a byte count and a digest.
        assert record.byte_count > 0
        assert len(record.sha256) == 64

    manifest = json.loads((out_dir / MANIFEST_NAME).read_text())
    assert len(manifest) == 2
    for row in manifest:
        assert set(row) == {"transport", "endpoint", "key", "byte_count",
                             "sha256", "fetched_at", "outcome"}


def test_recorded_transport_replays_what_was_captured(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _make_tree(source_root)
    source = LocalTransport(source_root)

    out_dir = tmp_path / "fixtures"
    record_fixtures(source, "incoming", out_dir, endpoint="test-endpoint")

    replay = RecordedTransport(out_dir)
    files = {f.key for f in replay.list("incoming")}
    assert files == {"incoming/a.csv", "incoming/sub/b.csv"}
    assert replay.fetch("incoming/a.csv") == b"a,b\n1,2\n"


def test_recorded_transport_never_lists_its_own_manifest(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _make_tree(source_root)
    out_dir = tmp_path / "fixtures"
    record_fixtures(LocalTransport(source_root), "incoming", out_dir, endpoint="e")

    replay = RecordedTransport(out_dir)
    keys = {f.key for f in replay.list("")}
    assert not any(key.endswith(MANIFEST_NAME) for key in keys)
