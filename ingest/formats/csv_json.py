"""The CSV/JSON reader, rebuilt on the role vocabulary (`ingest/schema.py`)
and the canonical builder (`ingest/normalize.py`) instead of the hardcoded
`_bank_column`/`_load_disputes` pair in `resolver/loaders.py`.

This is an INDEPENDENT second implementation of the same six-file contract,
not a wrapper around `resolver.loaders.load` -- that delegation was Phase A0's
placeholder, kept only as the ground truth `ingest/tests/test_conformance.py`
checks this reader against. Two implementations converging on 45/45 datasets
is stronger evidence than one implementation trusting itself.

`disputes.json`'s shape-dispatch (bare array vs. `{"items": [...]}`, duplicate
id, missing id) is not role-based -- it is a JSON envelope question, not a
column question -- so it is re-derived here rather than routed through
`schema.py`. The three raise conditions match `resolver/loaders.py::_load_disputes`
because they are the same defects Sec.71 closed, not a re-litigation of them.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ingest.normalize import (build_bank_line, build_dataset,
                               build_gstr2b_line, build_settlement_entry)
from ingest.schema import (BANK_ROLES, ERP_ROLES, GSTR2B_ROLES,
                            SETTLEMENT_REPORT_ROLES, resolve_role)
from resolver.loaders import FORBIDDEN, GroundTruthAccess


def _load_disputes(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text())

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and "items" in payload:
        items = payload["items"]
    else:
        found = (f"object with keys {sorted(payload)!r}"
                 if isinstance(payload, dict) else type(payload).__name__)
        raise ValueError(
            f"{path.name}: expected a bare array or an object carrying "
            f"'items'; found {found}.")

    if not isinstance(items, list):
        raise ValueError(
            f"{path.name}: 'items' must be an array, found "
            f"{type(items).__name__}")

    disputes: dict[str, dict] = {}
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(
                f"{path.name}: item {position} is "
                f"{type(item).__name__}, expected an object")
        key = item.get("id") or item.get("dispute_id") or ""
        if not key:
            raise ValueError(
                f"{path.name}: item {position} carries neither 'id' nor "
                f"'dispute_id'.")
        if key in disputes:
            raise ValueError(
                f"{path.name}: duplicate dispute id {key!r} at item "
                f"{position}.")
        disputes[key] = item
    return disputes


def load(directory: Path) -> "resolver.loaders.Dataset":  # noqa: F821 (string annotation)
    directory = Path(directory)
    for name in FORBIDDEN:
        if directory.name == name:
            raise GroundTruthAccess(name)

    rows = json.loads((directory / "recon_combined.json").read_text())["items"]

    bank = []
    bank_path = directory / "bank_statement.csv"
    with bank_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        ref_col = resolve_role(BANK_ROLES[0], fieldnames)
        date_col = resolve_role(BANK_ROLES[1], fieldnames)
        for index, line in enumerate(reader):
            bank.append(build_bank_line(
                index=index,
                reference=line.get(ref_col),
                value_date_text=line[date_col],
                narration=line.get("narration", ""),
                amount_text=line["amount"]))

    report: dict[str, dict] = {}
    report_path = directory / "settlement_report.csv"
    if report_path.exists():
        with report_path.open(newline="") as handle:
            for position, line in enumerate(csv.DictReader(handle)):
                settlement_id = line["settlement_id"]
                if settlement_id in report:
                    raise ValueError(
                        f"{report_path.name}: duplicate settlement_id "
                        f"{settlement_id!r} at row {position}.")
                report[settlement_id] = build_settlement_entry(
                    reported_reference=line.get("reported_reference", ""),
                    reported_amount_text=line["reported_amount"],
                    initiated_at=line.get("initiated_at", ""),
                    status=line.get("status", ""))

    orders: set[str] = set()
    erp_path = directory / "erp_orders.csv"
    if erp_path.exists():
        with erp_path.open(newline="") as handle:
            orders = {line["order_id"] for line in csv.DictReader(handle)}

    disputes: dict[str, dict] = {}
    dispute_path = directory / "disputes.json"
    if dispute_path.exists():
        disputes = _load_disputes(dispute_path)

    gstr2b = []
    gstr2b_path = directory / "gstr2b.csv"
    if gstr2b_path.exists():
        with gstr2b_path.open(newline="") as handle:
            for line in csv.DictReader(handle):
                gstr2b.append(build_gstr2b_line(
                    gstin=line["gstin"], invoice_no=line["invoice_no"],
                    invoice_date_text=line["invoice_date"],
                    taxable_value_text=line["taxable_value"],
                    igst_text=line["igst"], cgst_text=line["cgst"],
                    sgst_text=line["sgst"], irn=line["irn"],
                    irn_generated_at=line["irn_generated_at"],
                    gstr1_filing_period=line["gstr1_filing_period"],
                    supplier_gstr3b_filed=line["supplier_gstr3b_filed"],
                    itc_availability=line["itc_availability"]))

    return build_dataset(name=directory.name, rows=rows, bank=bank,
                          settlement_report=report,
                          erp_order_ids=frozenset(orders),
                          disputes=disputes, gstr2b=gstr2b)
