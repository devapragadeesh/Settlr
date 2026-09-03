"""CAMT.053 round-trip against every real `bank_statement.csv` on disk, plus
the XXE/entity-expansion refusal this format's docstring promises.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ingest.formats.camt053 import load_bank_lines
from ingest.formats.csv_json import load as load_csv_json
from resolver.loaders import _bank_column

ROOT = Path(__file__).resolve().parent.parent.parent
NS = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"


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


def _write_camt053_from_csv(csv_path: Path, xml_path: Path) -> None:
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or ()
        ref_col = _bank_column("reference", list(fieldnames), csv_path)
        date_col = _bank_column("value_date", list(fieldnames), csv_path)
        rows = list(reader)

    ET.register_namespace("", NS)
    document = ET.Element(f"{{{NS}}}Document")
    stmt = ET.SubElement(ET.SubElement(document, f"{{{NS}}}BkToCstmrStmt"), f"{{{NS}}}Stmt")

    for row in rows:
        amount = float(row["amount"])
        entry = ET.SubElement(stmt, f"{{{NS}}}Ntry")
        amt_el = ET.SubElement(entry, f"{{{NS}}}Amt", Ccy="INR")
        amt_el.text = format(abs(amount), ".2f")
        ind_el = ET.SubElement(entry, f"{{{NS}}}CdtDbtInd")
        ind_el.text = "CRDT" if amount > 0 else "DBIT"
        val_dt = ET.SubElement(entry, f"{{{NS}}}ValDt")
        ET.SubElement(val_dt, f"{{{NS}}}Dt").text = row[date_col]
        ref_el = ET.SubElement(entry, f"{{{NS}}}NtryRef")
        ref_el.text = row.get(ref_col) or ""
        details = ET.SubElement(ET.SubElement(entry, f"{{{NS}}}NtryDtls"), f"{{{NS}}}TxDtls")
        ET.SubElement(details, f"{{{NS}}}AddtlNtryInf").text = row.get("narration") or ""

    ET.ElementTree(document).write(xml_path, encoding="unicode", xml_declaration=True)


@pytest.mark.parametrize("directory", DATASET_DIRS, ids=lambda d: str(d.relative_to(ROOT)))
def test_camt053_round_trip_matches_csv(directory: Path, tmp_path: Path) -> None:
    want = load_csv_json(directory).bank

    xml_path = tmp_path / "statement.xml"
    _write_camt053_from_csv(directory / "bank_statement.csv", xml_path)
    got = load_bank_lines(xml_path)

    assert got == want


def test_a_doctype_declaration_is_refused_before_parsing(tmp_path: Path) -> None:
    # A textbook billion-laughs payload. If this ever reached the XML parser
    # the test process would hang or exhaust memory; the assertion is that it
    # never gets that far.
    payload = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<Document><BkToCstmrStmt><Stmt>&lol3;</Stmt></BkToCstmrStmt></Document>
"""
    path = tmp_path / "bomb.xml"
    path.write_text(payload)
    with pytest.raises(ValueError, match="DOCTYPE"):
        load_bank_lines(path)


def test_an_entry_missing_credit_debit_indicator_raises(tmp_path: Path) -> None:
    xml = f"""<?xml version="1.0"?>
<Document xmlns="{NS}"><BkToCstmrStmt><Stmt>
  <Ntry><Amt Ccy="INR">100.00</Amt></Ntry>
</Stmt></BkToCstmrStmt></Document>
"""
    path = tmp_path / "bad.xml"
    path.write_text(xml)
    with pytest.raises(ValueError):
        load_bank_lines(path)
