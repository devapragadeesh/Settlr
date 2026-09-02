"""Sanity checks on the `recon_combined.json` corruption harness itself.

These do NOT call `resolver`/`matching` -- that is `test_resolver_survives.py`
and `test_matching_survives.py`, which sweep every case in `cases.py`
(including the ones defined here) through both packages' real entry points
and apply the three-bucket rubric. This file only proves each mutation is a
one-line, well-isolated corruption of the known-good baseline: exactly what
`DECISIONS.md` 52 / `conftest.py` promise, checked mechanically rather than
by eyeballing `cases.py`.
"""

from __future__ import annotations

import json

import pytest

from .cases import RECON_CASES


@pytest.mark.parametrize("case", RECON_CASES, ids=lambda c: c.name)
def test_mutation_touches_only_recon_combined(case, resolver_case_dir):
    before = {p.name: p.read_bytes() for p in resolver_case_dir.iterdir()}
    case.mutate(resolver_case_dir)
    after = {p.name: p.read_bytes() for p in resolver_case_dir.iterdir()}
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed <= {"recon_combined.json"}, (
        f"{case.name} touched {changed}, expected at most recon_combined.json")
    assert changed, f"{case.name} did not change recon_combined.json at all"


def test_truncated_json_is_actually_invalid(resolver_case_dir):
    from .cases import _truncated_json
    _truncated_json(resolver_case_dir)
    text = (resolver_case_dir / "recon_combined.json").read_text()
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)


def test_missing_items_key_is_actually_missing(resolver_case_dir):
    from .cases import _missing_items_key
    _missing_items_key(resolver_case_dir)
    data = json.loads((resolver_case_dir / "recon_combined.json").read_text())
    assert "items" not in data


def test_empty_items_array_is_actually_empty(resolver_case_dir):
    from .cases import _empty_items_array
    _empty_items_array(resolver_case_dir)
    data = json.loads((resolver_case_dir / "recon_combined.json").read_text())
    assert data["items"] == []


def test_duplicate_entity_id_is_actually_duplicated(resolver_case_dir):
    from .cases import _duplicate_entity_id
    _duplicate_entity_id(resolver_case_dir)
    data = json.loads((resolver_case_dir / "recon_combined.json").read_text())
    ids = [item["entity_id"] for item in data["items"]]
    assert len(ids) != len(set(ids)), "expected a duplicated entity_id"


def test_negative_amount_is_actually_negative(resolver_case_dir):
    from .cases import _negative_amount
    _negative_amount(resolver_case_dir)
    data = json.loads((resolver_case_dir / "recon_combined.json").read_text())
    assert data["items"][0]["credit"] < 0


def test_settlement_id_null_vs_absent_are_different_artefacts(
        resolver_baseline, tmp_path):
    """`Dataset.rows_carry_settlement_id` (`resolver/loaders.py`) checks KEY
    PRESENCE, not truthiness, precisely so these two cases are distinguishable
    -- confirmed here at the fixture level, each on its own clone."""
    from .conftest import clone_dataset
    from .cases import _settlement_id_null, _settlement_id_absent

    null_dir = clone_dataset(resolver_baseline, tmp_path / "null")
    _settlement_id_null(null_dir)
    null_item = next(
        i for i in json.loads((null_dir / "recon_combined.json").read_text())["items"]
        if i["entity_id"] == "pay_LP8P7EnsoBgB5L")
    assert "settlement_id" in null_item
    assert null_item["settlement_id"] is None

    absent_dir = clone_dataset(resolver_baseline, tmp_path / "absent")
    _settlement_id_absent(absent_dir)
    absent_item = next(
        i for i in json.loads((absent_dir / "recon_combined.json").read_text())["items"]
        if i["entity_id"] == "pay_LP8P7EnsoBgB5L")
    assert "settlement_id" not in absent_item
