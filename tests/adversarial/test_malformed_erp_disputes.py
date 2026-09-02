"""Sanity checks on the `erp_orders.csv` / `disputes.json` corruption
harness, and the disputes.json shape handling in the two loaders.

**The dual-handling gap this module was written to document is CLOSED
(2026-09-03).** It used to read:

    payload.get("items", payload if isinstance(payload, list) else [])

which handled a bare array (the `isinstance` branch) OR `{"items": [...]}`
(the `.get` hits), and silently returned `[]` for anything else -- a JSON
object that is not `{"items": [...]}` hit neither branch, so every dispute in
the file was dropped, dispute id and all, without so much as a
`len(disputes) == 0` looking wrong. `_malformed_disputes_shape` in `cases.py`
writes exactly that shape.

`resolver.loaders._load_disputes` now dispatches on the shape explicitly and
raises `ValueError` on anything it does not recognise, rather than treating an
unrecognised file as an empty dispute set. It also refuses an item carrying
neither `id` nor `dispute_id` (which used to collapse to the key `""`) and a
repeated dispute id (which used to overwrite silently).

`matching.loaders.load` remains unconditional -- `json.loads(...)["items"]` --
and raises `KeyError` on both the bare-array and the object-without-"items"
shapes. `matching/` is frozen and is not changed; the two packages now agree
that this file is malformed, and differ only in which exception says so.
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


def test_resolver_refuses_the_unhandled_shape(resolver_case_dir):
    """The finding named in this module's docstring, now closed and pinned
    from the other side: `resolver.loaders.load` RAISES on this shape rather
    than returning an empty dispute set.

    Was `test_resolver_silently_drops_every_dispute_on_the_unhandled_shape`,
    which asserted `dataset.disputes == {}`. If this assertion is what fails,
    the loader stopped refusing the shape -- fix the loader, and update
    `run_adversarial.py`'s observations bullet with it. Do not relax it back.
    """
    from .cases import _malformed_disputes_shape
    _malformed_disputes_shape(resolver_case_dir)

    original_count = len(
        json.loads((resolver_case_dir / "disputes.json").read_text()))
    assert original_count > 0

    from resolver.loaders import load
    with pytest.raises(ValueError) as excinfo:
        load(resolver_case_dir)
    # the message must name the file and the shape, not just fail
    assert "disputes.json" in str(excinfo.value)
    assert "items" in str(excinfo.value)


def test_dispute_missing_id_is_refused_not_collapsed_to_one_key(
        resolver_case_dir):
    """`item.get("id") or item.get("dispute_id", "")` used to map EVERY
    dispute missing both keys to the same `""` key, so a second such item
    silently overwrote the first.

    That key is not inert. `resolver/breaks.py` reads back with
    `disputes.get(row.get("dispute_id") or "")`, so every payment row with no
    `dispute_id` -- 94% of recon rows -- probes `""` too. A single item landing
    there would have reclassified almost the whole non-disputed population as
    `UNEXPECTED_CHANGE`. The loader now refuses the item instead.

    Was `test_dispute_missing_id_collapses_to_one_key`, which asserted
    `"" in dataset.disputes`.
    """
    from .cases import _dispute_missing_id
    _dispute_missing_id(resolver_case_dir)
    data = json.loads((resolver_case_dir / "disputes.json").read_text())
    items = data.get("items", data if isinstance(data, list) else [])
    assert "id" not in items[0]
    assert "dispute_id" not in items[0]

    from resolver.loaders import load
    with pytest.raises(ValueError) as excinfo:
        load(resolver_case_dir)
    assert "disputes.json" in str(excinfo.value)


def test_a_duplicate_dispute_id_is_refused(resolver_case_dir):
    """The third silent failure in the same two lines: dict assignment is
    last-write-wins, so a repeated dispute id discarded the earlier item.

    Not reachable through `DISPUTES_CASES` -- that needs a two-item mutation
    and the sweep corrupts one field at a time -- so it is exercised directly
    here rather than left as a note, which is what the old docstring did.
    """
    path = resolver_case_dir / "disputes.json"
    payload = json.loads(path.read_text())
    items = payload["items"]
    assert len(items) >= 1
    payload["items"] = [items[0], dict(items[0])]
    path.write_text(json.dumps(payload))

    from resolver.loaders import load
    with pytest.raises(ValueError) as excinfo:
        load(resolver_case_dir)
    assert "duplicate dispute id" in str(excinfo.value)
