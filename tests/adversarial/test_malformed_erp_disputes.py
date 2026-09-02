"""Sanity checks on the `erp_orders.csv` / `disputes.json` corruption
harness, and the disputes.json dual-handling gap between the two loaders.

`resolver.loaders.load`:
    payload.get("items", payload if isinstance(payload, list) else [])
handles a bare array (falls through to the `isinstance` branch) OR
`{"items": [...]}` (the `.get` hits). A JSON object that is NOT
`{"items": [...]}` hits neither: `.get("items", ...)` returns the default
`[]` because `"items"` is absent AND `payload` is not a list, so the default
itself is `[]` -- every dispute in the file is silently dropped, dispute id
and all, without so much as a `len(disputes) == 0` looking wrong.

`matching.loaders.load` is unconditional: `json.loads(...)["items"]`. It
handles NEITHER a bare array NOR the object-without-"items" shape -- both
raise `KeyError`/nothing-to-index. So the shape `_malformed_disputes_shape`
in `cases.py` writes (a bare object keyed by dispute id, not `{"items":
[...]}`) is the one shape genuinely outside what `resolver` handles
gracefully: it loads with an EMPTY disputes dict and no error at all.
"""

from __future__ import annotations

import json

import pytest

from .cases import DISPUTES_CASES


@pytest.mark.parametrize("case", DISPUTES_CASES, ids=lambda c: c.name)
def test_mutation_touches_only_disputes(case, resolver_case_dir):
    before = {p.name: p.read_bytes() for p in resolver_case_dir.iterdir()}
    case.mutate(resolver_case_dir)
    after = {p.name: p.read_bytes() for p in resolver_case_dir.iterdir()}
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed <= {"disputes.json"}
    assert changed, f"{case.name} did not change disputes.json at all"


def test_malformed_shape_is_neither_bare_array_nor_items_wrapper(
        resolver_case_dir):
    from .cases import _malformed_disputes_shape
    _malformed_disputes_shape(resolver_case_dir)
    data = json.loads((resolver_case_dir / "disputes.json").read_text())
    assert isinstance(data, dict)
    assert "items" not in data
    assert len(data) > 0, "the case should keep the disputes, just reshape them"


def test_resolver_silently_drops_every_dispute_on_the_unhandled_shape(
        resolver_case_dir):
    """The finding named in this module's docstring, confirmed directly
    against `resolver.loaders.load`: it does not raise, and it does not
    warn -- `dataset.disputes` is simply empty."""
    from .cases import _malformed_disputes_shape
    _malformed_disputes_shape(resolver_case_dir)

    original_count = len(
        json.loads((resolver_case_dir / "disputes.json").read_text()))
    assert original_count > 0

    from resolver.loaders import load
    dataset = load(resolver_case_dir)
    assert dataset.disputes == {}, (
        "resolver.loaders.load no longer silently empties disputes on this "
        "shape -- update this test and the corresponding "
        "ADVERSARIAL_FINDINGS.md paragraph rather than deleting the check")


def test_dispute_missing_id_collapses_to_one_key(resolver_case_dir):
    """`item.get("id") or item.get("dispute_id", "")` maps EVERY dispute
    missing both keys to the same `""` key -- a second such dispute would
    silently overwrite the first in `dataset.disputes`. Confirmed for the
    single-item case the fixture produces; the collision itself needs two
    such items, which is outside this case's one-field-mutation scope and is
    just noted here."""
    from .cases import _dispute_missing_id
    _dispute_missing_id(resolver_case_dir)
    data = json.loads((resolver_case_dir / "disputes.json").read_text())
    items = data.get("items", data if isinstance(data, list) else [])
    assert "id" not in items[0]
    assert "dispute_id" not in items[0]

    from resolver.loaders import load
    dataset = load(resolver_case_dir)
    assert "" in dataset.disputes
