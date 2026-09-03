"""JSONL and paginated-JSON round-trip against every `recon_combined.json` on
disk, plus the pagination-sequence and malformed-line refusals.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.formats.jsonl import load_items, load_paginated_items

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


def _recon_items(directory: Path) -> list[dict]:
    payload = json.loads((directory / "recon_combined.json").read_text())
    return payload["items"]


@pytest.mark.parametrize("directory", DATASET_DIRS, ids=lambda d: str(d.relative_to(ROOT)))
def test_jsonl_round_trip_matches_recon_combined(directory: Path, tmp_path: Path) -> None:
    want = _recon_items(directory)

    jsonl_path = tmp_path / "recon.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(item) for item in want) + "\n")

    assert load_items(jsonl_path) == want


@pytest.mark.parametrize("directory", DATASET_DIRS, ids=lambda d: str(d.relative_to(ROOT)))
def test_paginated_json_round_trip_matches_recon_combined(directory: Path, tmp_path: Path) -> None:
    want = _recon_items(directory)

    page_size = max(1, len(want) // 3 or 1)
    pages = [want[i:i + page_size] for i in range(0, len(want), page_size)] or [[]]

    paths = []
    for position, page_items in enumerate(pages):
        has_more = position < len(pages) - 1
        page_path = tmp_path / f"page_{position}.json"
        page_path.write_text(json.dumps({"items": page_items, "has_more": has_more}))
        paths.append(page_path)

    assert load_paginated_items(paths) == want


def test_a_bare_json_array_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "bare.json"
    path.write_text(json.dumps([{"id": "a"}, {"id": "b"}]))
    assert load_items(path) == [{"id": "a"}, {"id": "b"}]


def test_a_non_last_page_claiming_has_more_false_is_refused(tmp_path: Path) -> None:
    p0 = tmp_path / "p0.json"
    p1 = tmp_path / "p1.json"
    p0.write_text(json.dumps({"items": [{"id": "a"}], "has_more": False}))
    p1.write_text(json.dumps({"items": [{"id": "b"}], "has_more": False}))
    with pytest.raises(ValueError, match="has_more"):
        load_paginated_items([p0, p1])


def test_the_last_page_claiming_has_more_true_is_refused(tmp_path: Path) -> None:
    p0 = tmp_path / "p0.json"
    p0.write_text(json.dumps({"items": [{"id": "a"}], "has_more": True}))
    with pytest.raises(ValueError, match="has_more"):
        load_paginated_items([p0])


def test_a_jsonl_line_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": "a"}\n[1, 2, 3]\n')
    with pytest.raises(ValueError, match="JSON object"):
        load_items(path)


def test_blank_lines_in_jsonl_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "blanks.jsonl"
    path.write_text('{"id": "a"}\n\n{"id": "b"}\n\n')
    assert load_items(path) == [{"id": "a"}, {"id": "b"}]
