"""Sanity checks on the `settlement_report.csv` corruption harness.

`settlement_report.csv` is resolver-only -- `matching/loaders.py` never opens
it (see `conftest.py`'s docstring), so every case here is scoped
`targets=frozenset({"resolver"})` in `cases.py` and only appears in
`test_resolver_survives.py`'s sweep.
"""

from __future__ import annotations

import csv

import pytest

from .cases import SETTLEMENT_REPORT_CASES


@pytest.mark.parametrize("case", SETTLEMENT_REPORT_CASES, ids=lambda c: c.name)
def test_mutation_touches_only_settlement_report(case, resolver_case_dir):
    before = {p.name: p.read_bytes() for p in resolver_case_dir.iterdir()}
    case.mutate(resolver_case_dir)
    after = {p.name: p.read_bytes() for p in resolver_case_dir.iterdir()}
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed <= {"settlement_report.csv"}
    assert changed, f"{case.name} did not change settlement_report.csv at all"


def test_duplicate_settlement_id_is_last_write_wins_in_the_loader(
        resolver_case_dir):
    """`resolver.loaders.load` builds `report` with a plain dict keyed by
    `settlement_id`: `report[line["settlement_id"]] = {...}` inside a loop
    over CSV rows in file order. A second row for the same `settlement_id`
    silently OVERWRITES the first -- last-write-wins, with no error and no
    signal in the returned `Dataset`. Asserted explicitly here rather than
    left implicit, per the task brief."""
    from .cases import _duplicate_settlement_id_report
    _duplicate_settlement_id_report(resolver_case_dir)

    with (resolver_case_dir / "settlement_report.csv").open(newline="") as handle:
        rows = [r for r in csv.DictReader(handle)
                if r["settlement_id"] == "setl_3XDSdIhVtpYs2i"]
    assert len(rows) == 2, "expected the case to append a second row"
    assert rows[0]["reported_amount"] != rows[1]["reported_amount"]

    from resolver.loaders import load
    dataset = load(resolver_case_dir)
    # exactly one entry survives, and it is the LAST row's data (1.00 rupee
    # == 100 paise), confirming last-write-wins rather than e.g. a merge or
    # a raised error on the collision.
    entry = dataset.settlement_report["setl_3XDSdIhVtpYs2i"]
    assert entry["reported_amount"] == 100, (
        "resolver.loaders.load's settlement_report dict no longer silently "
        "overwrites on a duplicate settlement_id -- update this assertion "
        "(and the corresponding paragraph in ADVERSARIAL_FINDINGS.md) to "
        "match the new behaviour rather than deleting the check")
