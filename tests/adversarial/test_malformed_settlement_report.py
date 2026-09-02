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


def test_duplicate_settlement_id_is_refused_not_overwritten(
        resolver_case_dir):
    """`resolver.loaders.load` used to build `report` with a plain dict keyed
    by `settlement_id` -- `report[line["settlement_id"]] = {...}` in file
    order -- so a second row for the same id silently OVERWROTE the first.
    Last-write-wins, no error, no signal in the returned `Dataset`.

    Closed 2026-09-03; the loader now raises. This feed is the PSP's
    attestation, the evidence a `Verified` composition is warranted by, so
    two contradicting claims about one settlement is a finding, not something
    to resolve by discarding whichever came first.

    Was `test_duplicate_settlement_id_is_last_write_wins_in_the_loader`,
    which asserted `entry["reported_amount"] == 100`. If this assertion is
    what fails, the loader stopped refusing the duplicate -- fix the loader
    and update `run_adversarial.py`'s observations bullet with it, rather
    than relaxing this back.
    """
    from .cases import _duplicate_settlement_id_report
    _duplicate_settlement_id_report(resolver_case_dir)

    with (resolver_case_dir / "settlement_report.csv").open(newline="") as handle:
        rows = [r for r in csv.DictReader(handle)
                if r["settlement_id"] == "setl_3XDSdIhVtpYs2i"]
    assert len(rows) == 2, "expected the case to append a second row"
    assert rows[0]["reported_amount"] != rows[1]["reported_amount"]

    from resolver.loaders import load
    with pytest.raises(ValueError) as excinfo:
        load(resolver_case_dir)
    message = str(excinfo.value)
    assert "settlement_report.csv" in message
    assert "setl_3XDSdIhVtpYs2i" in message
