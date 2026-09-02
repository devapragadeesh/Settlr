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

def test_the_two_paise_parsers_agree():
    """`matching/money.py::paise` and `resolver/loaders.py::paise` parse the
    SAME kind of cell (a rupee string from a CSV) and must not disagree about
    what it means.

    They used to. `matching.money.paise` matched
    `_RUPEES = r"^(-?)(\\d+)(?:\\.(\\d{1,2}))?$"` and RAISED `ValueError` on a
    third decimal digit. `resolver.loaders.paise` did string surgery with no
    validation at all -- `int((frac + "00")[:2])` always took exactly the first
    two decimal digits -- so `"7612.9951"` became `7612.99` silently: not
    rounded, not an error, the tail simply dropped.

    That was a correctness difference, not a crash difference, and the loss
    always ran in the same direction. Fixed 2026-09-03 by giving
    `resolver.loaders.paise` the identical grammar. The two are duplicated
    rather than shared because `resolver/` may not import `matching/` --
    `resolver/tests/test_isolation.py`'s FORBIDDEN set keeps the frozen cascade
    independently frozen -- so this test is what stops the duplication drifting
    back apart. If it fails, the two parsers have diverged again; fix the
    parser, do not relax the test.
    """
    from matching.money import paise as matching_paise
    from resolver.loaders import paise as resolver_paise

    def outcome(fn, value):
        try:
            return ("ok", fn(value))
        except ValueError:
            return ("ValueError", None)

    accepted = ["0", "1", "100", "7612.99", "-5.5", "-0.01", "0.00",
                "999999999.99", "42.5", "-7"]
    rejected = ["7612.9951", "7612.996", "0.999", "", "   ", "abc", "1.",
                ".5", "+5", "1.2.3", "-", "1 2", "1e5"]

    for value in accepted + rejected:
        assert outcome(matching_paise, value) == outcome(resolver_paise, value), (
            f"the two paise parsers disagree on {value!r} -- "
            f"matching={outcome(matching_paise, value)} "
            f"resolver={outcome(resolver_paise, value)}")

    # and the agreement is not the trivial one of both rejecting everything
    assert outcome(matching_paise, "7612.99") == ("ok", 761299)
    assert outcome(resolver_paise, "7612.99") == ("ok", 761299)


def test_over_precision_is_rejected_not_truncated():
    """The specific cell that used to lose precision silently. Both parsers
    now refuse it, so a malformed money cell fails loudly on either side.

    Replaces `test_paise_truncate_is_floor_not_round`, which asserted the old
    truncating behaviour ("7612.996" -> 761299, floor rather than round) and
    is obsolete now that the value raises instead.
    """
    from matching.money import paise as matching_paise
    from resolver.loaders import paise as resolver_paise

    for value in ("7612.9951", "7612.996", "0.999"):
        with pytest.raises(ValueError):
            matching_paise(value)
        with pytest.raises(ValueError):
            resolver_paise(value)


def test_the_strict_grammar_accepts_every_money_cell_in_the_repo():
    """The fix is only safe because nothing in the corpus needed the leniency.

    Walks every money column of every dataset CSV in the repository and asserts
    the strict grammar accepts all of them -- i.e. no published figure can move
    as a result of tightening the parser. Measured at the time of the change:
    6,374 cells across 168 CSVs, zero rejected.
    """
    from resolver.loaders import paise as resolver_paise

    repo_root = Path(__file__).resolve().parents[2]
    targets = {
        "bank_statement.csv": ("amount",),
        "settlement_report.csv": ("reported_amount",),
        "gstr2b.csv": ("taxable_value", "igst", "cgst", "sgst"),
    }

    checked = 0
    for filename, columns in targets.items():
        for path in repo_root.rglob(filename):
            if ".venv" in path.parts or ".claude" in path.parts:
                continue
            with path.open(newline="") as handle:
                for row in csv.DictReader(handle):
                    for column in columns:
                        if column not in row:
                            continue
                        checked += 1
                        try:
                            resolver_paise(row[column])
                        except ValueError:  # pragma: no cover - the assertion
                            raise AssertionError(
                                f"the strict grammar rejects a REAL cell: "
                                f"{path}:{column}={row[column]!r} -- tightening "
                                f"the parser would move a published figure")

    assert checked > 6000, (
        f"only {checked} money cells found; this test is meant to sweep the "
        f"whole corpus and something is not being walked")


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


# ---------------------------------------------------------------------------
# bank_statement.csv column vocabulary -- the two-schema divergence
# ---------------------------------------------------------------------------

def test_both_bank_column_vocabularies_load():
    """`bank_statement.csv` ships under two header spellings in this repo and
    the resolver must read both.

    The corpus generator emits `bank_reference,value_date`; the frozen
    `engine/generator.py` emitted `utr,date`, and `engine/data`,
    `holdout/data` and all eight `scale/data_*` fixtures are frozen at that
    spelling. `resolver/loaders.py` used to hardcode the first, so it raised
    `KeyError: 'value_date'` on ten dataset directories -- the held-out set
    and every throughput fixture. That is the mechanical reason resolver
    throughput at scale was never measured.

    Fixed 2026-09-03. If this fails, the resolver has stopped reading one of
    the two vocabularies; fix the loader, do not narrow the test.
    """
    from resolver.loaders import load

    repo_root = Path(__file__).resolve().parents[2]
    new_schema = repo_root / "corpus/datasets/A20_B75_Cmax"
    old_schema = repo_root / "engine/data"

    for directory in (new_schema, old_schema):
        header = (directory / "bank_statement.csv").read_text().splitlines()[0]
        dataset = load(directory)
        assert dataset.bank, f"{directory.name}: loaded no bank lines ({header})"
        assert dataset.rows, f"{directory.name}: loaded no recon rows"

    # and the two really are different vocabularies, not the same file twice
    assert "value_date" in (new_schema / "bank_statement.csv").read_text()
    assert "utr," in (old_schema / "bank_statement.csv").read_text()


def test_a_missing_bank_date_column_is_refused_not_defaulted():
    """Accepting two spellings must not become accepting anything. A header
    carrying neither spelling of a role raises, naming both accepted names."""
    from resolver.loaders import _bank_column

    path = Path("bank_statement.csv")
    with pytest.raises(ValueError) as excinfo:
        _bank_column("value_date", ["utr", "narration", "amount"], path)
    assert "value_date" in str(excinfo.value) and "date" in str(excinfo.value)

    # both spellings of one role present is ambiguous, and is refused rather
    # than resolved by preference order
    with pytest.raises(ValueError) as excinfo:
        _bank_column("value_date", ["value_date", "date", "amount"], path)
    assert "ambiguous" in str(excinfo.value)

    # the ordinary cases still resolve
    assert _bank_column("value_date", ["value_date", "amount"], path) == "value_date"
    assert _bank_column("value_date", ["date", "amount"], path) == "date"
    assert _bank_column("reference", ["utr", "amount"], path) == "utr"
    assert _bank_column("reference", ["bank_reference"], path) == "bank_reference"


def test_every_dataset_in_the_repo_loads():
    """The whole point of the fix, pinned: no dataset directory in the
    repository is unreadable by the resolver's loader.

    Was 35 of 45 before 2026-09-03 -- the ten failures were `engine/data`,
    `holdout/data` and the eight `scale/data_*` throughput fixtures.
    """
    import glob
    from resolver.loaders import load

    repo_root = Path(__file__).resolve().parents[2]
    directories = sorted(
        {Path(p).parent for p in glob.glob(
            str(repo_root / "**/recon_combined.json"), recursive=True)
         if ".claude" not in Path(p).parts})
    assert len(directories) >= 45, f"only found {len(directories)} datasets"

    failures = []
    for directory in directories:
        try:
            load(directory)
        except Exception as exc:  # noqa: BLE001 - the failure IS the finding
            failures.append(f"{directory}: {type(exc).__name__}: {exc}")
    assert not failures, "datasets the resolver cannot read:\n" + "\n".join(failures)
