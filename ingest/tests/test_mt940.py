"""MT940 round-trip against every real `bank_statement.csv` on disk."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ingest.formats.csv_json import load as load_csv_json
from ingest.formats.mt940 import load_bank_lines
from resolver.loaders import _bank_column

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


def _write_mt940_from_csv(csv_path: Path, mt_path: Path) -> None:
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or ()
        ref_col = _bank_column("reference", list(fieldnames), csv_path)
        date_col = _bank_column("value_date", list(fieldnames), csv_path)
        rows = list(reader)

    lines: list[str] = [":20:STMT0001", ":25:ACCOUNT/0001", ":28C:1/1"]
    for row in rows:
        amount = float(row["amount"])
        mark = "C" if amount > 0 else "D"
        year, month, day = row[date_col].split("-")
        yymmdd = year[2:] + month + day
        amount_text = format(abs(amount), ".2f").replace(".", ",")
        ref = (row.get(ref_col) or "").strip()
        # Owner reference goes directly after the type code, with no "//" --
        # "//" introduces a SEPARATE bank-assigned reference (see
        # ingest/formats/mt940.py's docstring). This repo's data has only one
        # reference per line, so it belongs in the owner-reference position.
        lines.append(f":61:{yymmdd}{mark}{amount_text}NTRF{ref}")
        narration = row.get("narration") or ""
        lines.append(f":86:{narration}")
    mt_path.write_text("\n".join(lines) + "\n")


@pytest.mark.parametrize("directory", DATASET_DIRS, ids=lambda d: str(d.relative_to(ROOT)))
def test_mt940_round_trip_matches_csv(directory: Path, tmp_path: Path) -> None:
    want = load_csv_json(directory).bank

    mt_path = tmp_path / "statement.sta"
    _write_mt940_from_csv(directory / "bank_statement.csv", mt_path)
    got = load_bank_lines(mt_path)

    assert got == want


def test_an_unrecognised_mark_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.sta"
    path.write_text(":61:2701060106X7612,99NTRF//REF1\n")
    with pytest.raises(ValueError):
        load_bank_lines(path)


def test_a_line_with_no_86_gets_empty_narration(tmp_path: Path) -> None:
    path = tmp_path / "no86.sta"
    path.write_text(":61:270106C100,00NTRF//REF1\n")
    lines = load_bank_lines(path)
    assert len(lines) == 1
    assert lines[0].narration == ""
    assert lines[0].amount_paise == 10000
