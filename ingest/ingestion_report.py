#!/usr/bin/env python3
"""Generate `ingest/INGESTION_REPORT.md` from a LIVE run of every adapter's
round-trip check, over every dataset directory on disk. Per `CLAUDE.md`:
"Reports are generated. If a number appears in a markdown file, a script
should have written it." No number in the output file is hand-typed.

    python3 -m ingest.ingestion_report

This does not call `resolve()` or read `ground_truth.json` anywhere -- it
only re-derives what `ingest/tests/*` already assert, outside of pytest, so
the counts in the report are traceable to the same checks the test suite
runs on every commit.
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

import openpyxl

from ingest.formats import camt053, csv_json, jsonl, mt940, xlsx
from resolver.loaders import _bank_column

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "ingest" / "INGESTION_REPORT.md"
JSON_PATH = ROOT / "ingest" / "ingestion_results.json"

CAMT_NS = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"


def _dataset_dirs() -> list[Path]:
    dirs = [ROOT / "engine" / "data", ROOT / "holdout" / "data"]
    dirs += sorted((ROOT / "scale").glob("data_*"))
    for family in ("datasets", "datasets_v2", "datasets_gst",
                    "datasets_gst_holdout", "datasets_bankside"):
        base = ROOT / "corpus" / family
        if base.exists():
            dirs += sorted(p for p in base.iterdir() if p.is_dir())
    return dirs


def _write_xlsx(csv_path: Path, out_path: Path) -> None:
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or ()
        ref_col = _bank_column("reference", list(fieldnames), csv_path)
        date_col = _bank_column("value_date", list(fieldnames), csv_path)
        rows = list(reader)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append([ref_col, date_col, "narration", "amount"])
    for row in rows:
        sheet.append([row.get(ref_col) or None,
                      datetime.date.fromisoformat(row[date_col]),
                      row.get("narration") or None, float(row["amount"])])
    workbook.save(out_path)


def _write_camt053(csv_path: Path, out_path: Path) -> None:
    import xml.etree.ElementTree as ET
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or ()
        ref_col = _bank_column("reference", list(fieldnames), csv_path)
        date_col = _bank_column("value_date", list(fieldnames), csv_path)
        rows = list(reader)
    ET.register_namespace("", CAMT_NS)
    document = ET.Element(f"{{{CAMT_NS}}}Document")
    stmt = ET.SubElement(ET.SubElement(document, f"{{{CAMT_NS}}}BkToCstmrStmt"), f"{{{CAMT_NS}}}Stmt")
    for row in rows:
        amount = float(row["amount"])
        entry = ET.SubElement(stmt, f"{{{CAMT_NS}}}Ntry")
        ET.SubElement(entry, f"{{{CAMT_NS}}}Amt", Ccy="INR").text = format(abs(amount), ".2f")
        ET.SubElement(entry, f"{{{CAMT_NS}}}CdtDbtInd").text = "CRDT" if amount > 0 else "DBIT"
        val_dt = ET.SubElement(entry, f"{{{CAMT_NS}}}ValDt")
        ET.SubElement(val_dt, f"{{{CAMT_NS}}}Dt").text = row[date_col]
        ET.SubElement(entry, f"{{{CAMT_NS}}}NtryRef").text = row.get(ref_col) or ""
        details = ET.SubElement(ET.SubElement(entry, f"{{{CAMT_NS}}}NtryDtls"), f"{{{CAMT_NS}}}TxDtls")
        ET.SubElement(details, f"{{{CAMT_NS}}}AddtlNtryInf").text = row.get("narration") or ""
    ET.ElementTree(document).write(out_path, encoding="unicode", xml_declaration=True)


def _write_mt940(csv_path: Path, out_path: Path) -> None:
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or ()
        ref_col = _bank_column("reference", list(fieldnames), csv_path)
        date_col = _bank_column("value_date", list(fieldnames), csv_path)
        rows = list(reader)
    lines = [":20:STMT0001", ":25:ACCOUNT/0001", ":28C:1/1"]
    for row in rows:
        amount = float(row["amount"])
        mark = "C" if amount > 0 else "D"
        year, month, day = row[date_col].split("-")
        amount_text = format(abs(amount), ".2f").replace(".", ",")
        ref = (row.get(ref_col) or "").strip()
        lines.append(f":61:{year[2:]}{month}{day}{mark}{amount_text}NTRF{ref}")
        lines.append(f":86:{row.get('narration') or ''}")
    out_path.write_text("\n".join(lines) + "\n")


def _round_trip_tally(name: str, writer, loader, tmp_root: Path, *,
                       extension: str) -> dict:
    dirs = _dataset_dirs()
    ok, failed = 0, []
    for directory in dirs:
        want = csv_json.load(directory).bank
        out_path = tmp_root / f"{name}_{directory.name}{extension}"
        try:
            writer(directory / "bank_statement.csv", out_path)
            got = loader(out_path)
        except Exception as error:  # noqa: BLE001 -- tallying, not asserting
            failed.append((str(directory.relative_to(ROOT)), repr(error)))
            continue
        if got == want:
            ok += 1
        else:
            failed.append((str(directory.relative_to(ROOT)), "mismatch"))
    return {"format": name, "total": len(dirs), "ok": ok, "failed": failed}


def _jsonl_tally() -> dict:
    dirs = _dataset_dirs()
    ok, failed = 0, []
    for directory in dirs:
        payload = json.loads((directory / "recon_combined.json").read_text())
        want = payload["items"]
        text = "\n".join(json.dumps(item) for item in want) + "\n"
        got = list(jsonl._iter_jsonl(text))
        if got == want:
            ok += 1
        else:
            failed.append((str(directory.relative_to(ROOT)), "mismatch"))
    return {"format": "jsonl", "total": len(dirs), "ok": ok, "failed": failed}


DROPPED_FIELDS = {
    "xlsx": "Sheets beyond the first are never read; only the bank role "
            "(reference, value_date, narration, amount) is populated.",
    "camt053": "Ccy (no second-currency field exists), CdtDbtInd as a "
               "standalone flag (folded into the amount's sign), non-Ntry "
               "statement-level data (GrpHdr, Bal, account identifiers).",
    "mt940": "The funds code, the transaction type code (NTRF etc.), the "
             "bank-assigned '//' reference when an owner reference is "
             "present, and :86: structured subfield tags.",
    "jsonl": "Nothing -- items round-trip as opaque dicts, unlike the "
             "bank-only formats above.",
}


def main() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        results = [
            _round_trip_tally("xlsx", _write_xlsx, xlsx.load_bank_lines,
                               tmp_root, extension=".xlsx"),
            _round_trip_tally("camt053", _write_camt053, camt053.load_bank_lines,
                               tmp_root, extension=".xml"),
            _round_trip_tally("mt940", _write_mt940, mt940.load_bank_lines,
                               tmp_root, extension=".sta"),
            _jsonl_tally(),
        ]

    lines = [
        "# INGESTION_REPORT.md",
        "",
        "Generated by `python3 -m ingest.ingestion_report`. Every number below "
        "comes from a live round-trip check run at generation time, not a "
        "hand-typed claim -- see `ingest/tests/*` for the pytest-integrated "
        "versions of these same checks.",
        "",
        "**These fixtures are synthetic**, generated from this repo's own "
        "`bank_statement.csv`/`recon_combined.json` files. A round trip proves "
        "each adapter is self-consistent with the CSV/JSON reader it is "
        "checked against, not that it correctly parses an arbitrary real "
        "bank's export. Where noted, real sample files would be strictly "
        "better evidence.",
        "",
        "## Round-trip results",
        "",
        "| format | total datasets | round-trips OK | failed |",
        "|---|---|---|---|",
    ]
    for result in results:
        lines.append(f"| {result['format']} | {result['total']} | "
                      f"{result['ok']} | {len(result['failed'])} |")

    lines += ["", "## What each adapter drops (named, not silent)", ""]
    for name, note in DROPPED_FIELDS.items():
        lines.append(f"- **{name}**: {note}")

    lines += [
        "",
        "## Adversarial coverage",
        "",
        "Each format's own test file (`ingest/tests/test_xlsx.py`, "
        "`test_camt053.py`, `test_mt940.py`) carries hand-written malformed-"
        "input cases honouring `DECISIONS.md` Sec.52's three-bucket rule "
        "(clean typed decline / uncaught exception / silent wrong answer -- "
        "only the third fails), including a real XXE/billion-laughs payload "
        "for CAMT.053. These are NOT yet integrated into "
        "`tests/adversarial/run_adversarial.py`'s shared bucket harness "
        "(`ADVERSARIAL_FINDINGS.md`), which is purpose-built around the "
        "resolver/matching classifiers -- extending it to four more formats "
        "is a named, deferred structural change, not folded in here to look "
        "more complete than it is.",
        "",
    ]

    any_failed = any(r["failed"] for r in results)
    if any_failed:
        lines += ["## Failures", ""]
        for result in results:
            for path, reason in result["failed"]:
                lines.append(f"- **{result['format']}** / `{path}`: {reason}")

    OUT_PATH.write_text("\n".join(lines) + "\n")
    JSON_PATH.write_text(json.dumps(
        {r["format"]: {"total": r["total"], "ok": r["ok"],
                        "failed": len(r["failed"])} for r in results},
        indent=1) + "\n")
    print(f"wrote {OUT_PATH}")
    print(f"wrote {JSON_PATH}")
    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
