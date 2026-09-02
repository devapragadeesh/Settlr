"""Sanity checks on the `bank_statement.csv` corruption harness, plus a
direct, package-level comparison of `matching.money.paise` vs
`resolver.loaders.paise` on over-precision decimal strings -- flagged in the
task brief as worth checking explicitly.

As in `test_malformed_recon.py`, the load/resolve/cascade sweep itself lives
in `test_resolver_survives.py` / `test_matching_survives.py`.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import pytest

from .cases import BANK_CASES, _date_and_ref_columns


@pytest.mark.parametrize("case", BANK_CASES, ids=lambda c: c.name)
def test_mutation_touches_only_bank_statement(case, resolver_case_dir):
    before = {p.name: p.read_bytes() for p in resolver_case_dir.iterdir()}
    case.mutate(resolver_case_dir)
    after = {p.name: p.read_bytes() for p in resolver_case_dir.iterdir()}
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed <= {"bank_statement.csv"}
    assert changed, f"{case.name} did not change bank_statement.csv at all"


def test_duplicate_bank_reference_is_actually_duplicated(resolver_case_dir):
    from .cases import _duplicate_bank_reference
    _duplicate_bank_reference(resolver_case_dir)
    with (resolver_case_dir / "bank_statement.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    refs = [r["bank_reference"] for r in rows if r["bank_reference"]]
    assert len(refs) != len(set(refs)), "expected a duplicated bank_reference"


def test_zero_row_file_has_header_only(resolver_case_dir):
    from .cases import _zero_row_bank_file
    _zero_row_bank_file(resolver_case_dir)
    with (resolver_case_dir / "bank_statement.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == []


def test_only_foreign_lines_shares_no_reference_with_settlement_report(
        resolver_case_dir):
    from .cases import _only_foreign_lines
    _only_foreign_lines(resolver_case_dir)
    with (resolver_case_dir / "bank_statement.csv").open(newline="") as handle:
        bank_refs = {r["bank_reference"] for r in csv.DictReader(handle)}
    with (resolver_case_dir / "settlement_report.csv").open(newline="") as handle:
        report_refs = {r["reported_reference"]
                       for r in csv.DictReader(handle) if r["reported_reference"]}
    assert not (bank_refs & report_refs)


# ---------------------------------------------------------------------------
# money.paise: truncate vs reject on over-precision decimal strings
# ---------------------------------------------------------------------------

def test_paise_truncate_vs_reject_over_precision():
    """`matching/money.py::paise` and `resolver/loaders.py::paise` both parse
    the SAME kind of cell (a rupee string from a CSV) and disagree on what
    "more than two decimal digits" means.

    `matching.money.paise` matches against `_RUPEES = r"^(-?)(\\d+)(?:\\.(\\d{1,2}))?$"`
    and RAISES `ValueError` on a third decimal digit -- a malformed cell fails
    loudly (its own docstring says so).

    `resolver.loaders.paise` does string surgery with no validation at all:
    `int((frac + "00")[:2])` always takes exactly the first two decimal
    digits and silently drops the rest. `"7612.9951"` truncates to
    `7612.99`, not `7612.995` rounded, and not an error -- the third and
    fourth digits are dropped with no signal.

    This is not a crash difference; it is a correctness difference. The
    frozen cascade fails loudly on this cell. The resolver accepts it and
    quietly discards 0.01 paise-scale precision -- the exact "does this
    degrade safely" question this whole suite is asking, isolated to one
    function call with no dataset or loader involved.
    """
    from matching.money import paise as matching_paise
    from resolver.loaders import paise as resolver_paise

    over_precision = "7612.9951"

    with pytest.raises(ValueError):
        matching_paise(over_precision)

    # resolver's paise does NOT raise -- it silently truncates to the first
    # two decimal digits, i.e. drops the "51" tail without complaint.
    truncated = resolver_paise(over_precision)
    assert truncated == 761299, (
        "resolver.loaders.paise's truncate behaviour changed -- if this "
        "assertion is what fails, the discrepancy documented in "
        "ADVERSARIAL_FINDINGS.md needs updating, not silencing")

    # explicit contrast: the same string parsed as if it were exactly
    # two decimal digits gives the identical result, proving the extra
    # digits were dropped rather than incorporated in any way (e.g. rounded).
    assert resolver_paise("7612.99") == truncated


def test_paise_truncate_is_floor_not_round(tmp_path):
    """`resolver.loaders.paise` truncates rather than rounds: "7612.996"
    (which a human would round to 7612.996 ~ 7613.00 at 2dp, or at minimum to
    7613.00 by round-half-up on the third digit) truncates DOWN to 7612.99,
    losing money in the direction that always favours truncation, never
    correct rounding."""
    from resolver.loaders import paise as resolver_paise

    assert resolver_paise("7612.996") == 761299
    assert resolver_paise("0.999") == 99


# ---------------------------------------------------------------------------
# large row count -- loader-level smoke case, not a throughput benchmark
# ---------------------------------------------------------------------------

def _write_large_bank_statement(directory: Path, rows: int) -> None:
    source = directory / "bank_statement.csv"
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames)
        template = list(reader)
    date_col, ref_col = _date_and_ref_columns(fieldnames)
    with source.open("w", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        base = template[0] if template else {}
        for i in range(rows):
            row = dict(base)
            row[ref_col] = f"SMOKE{i:07d}"
            row["amount"] = "1.00"
            writer.writerow(row)


def test_resolver_loader_smoke_large_bank_file(resolver_case_dir):
    """Not a throughput benchmark (that is `scale/`); just confirms the
    loader does not hang or blow up on row count alone."""
    _write_large_bank_statement(resolver_case_dir, 5000)
    from resolver.loaders import load
    began = time.perf_counter()
    dataset = load(resolver_case_dir)
    elapsed = time.perf_counter() - began
    assert len(dataset.bank) == 5000
    assert elapsed < 30, f"resolver.loaders.load took {elapsed:.1f}s for 5000 rows"


def test_matching_loader_smoke_large_bank_file(matching_case_dir):
    _write_large_bank_statement(matching_case_dir, 5000)
    from matching.loaders import load
    began = time.perf_counter()
    dataset = load(matching_case_dir)
    elapsed = time.perf_counter() - began
    assert len(dataset.bank) == 5000
    assert elapsed < 30, f"matching.loaders.load took {elapsed:.1f}s for 5000 rows"
