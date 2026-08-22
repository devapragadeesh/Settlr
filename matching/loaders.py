"""Load the frozen dataset.

Read-only. This package never writes to the frozen data directory and never
reads the isolated answer key -- see `tests/test_no_leakage.py`, which enforces
that structurally rather than by convention.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .money import paise

IST = timezone(timedelta(hours=5, minutes=30))
DATA = Path(__file__).resolve().parent.parent / "engine" / "data"


def resolve_row_id(row: dict) -> str | None:
    """The verified id-resolution rule: `entity_id if payment else payment_id`.

    `payment_id` is null ON payment rows and populated only on rows POINTING AT
    a payment, so reading `payment_id` blindly loses every payment.
    """
    return row["entity_id"] if row["type"] == "payment" else row["payment_id"]


def has_credit_type(row: dict) -> bool:
    """`credit_type` is ABSENT on adjustment rows, not null.

    Key presence, never value -- `row.get("credit_type") is None` cannot tell
    "omitted" from "present and null", and the two mean different things.
    """
    return "credit_type" in row


def is_failed(row: dict) -> bool:
    """Failed payments carry fee: null, tax: null -- NOT 0.

    They never appear in a batch and must be filtered before any arithmetic:
    summing `None` raises, and coercing it to 0 invents a fee.
    """
    return row["type"] == "payment" and row["fee"] is None


def is_unjoinable_adjustment(row: dict) -> bool:
    """Adjustment rows have no payment_id, order_id or method.

    Unjoinable BY CONSTRUCTION. A matcher that finds a partner for one has
    produced a false positive.
    """
    return (row["type"] == "adjustment"
            and row["payment_id"] is None
            and row["order_id"] is None
            and row["method"] is None)


def notes_of(row: dict) -> dict:
    """Defensive `notes` access.

    This dataset only ever emits `{}` or `[]`, but the real API is fully
    polymorphic (object | array | string | null). The dataset's narrower shape
    does not generalise, so this normalises rather than assuming.
    """
    value = row.get("notes")
    return value if isinstance(value, dict) else {}


def to_date(unix_ts: int) -> date:
    return datetime.fromtimestamp(unix_ts, IST).date()


@dataclass(frozen=True, slots=True)
class BankLine:
    index: int
    utr: str          # "" when the column is blank -- the join key is GONE
    value_date: date
    narration: str
    amount: int       # paise

    @property
    def has_join_key(self) -> bool:
        return bool(self.utr)


@dataclass(frozen=True, slots=True)
class ErpOrder:
    order_id: str
    invoice_no: str
    gstin: str        # "" for B2C
    amount: int       # paise
    invoice_date: date


@dataclass(frozen=True, slots=True)
class Gstr2bLine:
    gstin: str
    invoice_no: str
    invoice_date: date
    taxable_value: int
    igst: int
    cgst: int
    sgst: int
    irn: str
    irn_generated_at: str
    gstr1_filing_period: str
    supplier_gstr3b_filed: str
    itc_availability: str

    @property
    def tax_total(self) -> int:
        return self.igst + self.cgst + self.sgst

    @property
    def has_irn(self) -> bool:
        return bool(self.irn.strip())


@dataclass(frozen=True, slots=True)
class Dataset:
    rows: list[dict]
    bank: list[BankLine]
    erp: list[ErpOrder]
    gstr2b: list[Gstr2bLine]
    disputes: list[dict]

    @property
    def rows_by_id(self) -> dict[str, dict]:
        return {row["entity_id"]: row for row in self.rows}

    def ledger_rows(self) -> list[dict]:
        """Rows that can carry money into a batch. Failed payments excluded."""
        return [row for row in self.rows if not is_failed(row)]


def load(data_dir: Path | None = None) -> Dataset:
    root = Path(data_dir) if data_dir else DATA
    rows = json.loads((root / "recon_combined.json").read_text())["items"]
    disputes = json.loads((root / "disputes.json").read_text())["items"]

    bank = []
    with (root / "bank_statement.csv").open(newline="") as handle:
        for index, line in enumerate(csv.DictReader(handle)):
            bank.append(BankLine(
                index=index,
                utr=line["utr"].strip(),
                value_date=date.fromisoformat(line["date"]),
                narration=line["narration"],
                amount=paise(line["amount"]),
            ))

    erp = []
    with (root / "erp_orders.csv").open(newline="") as handle:
        for line in csv.DictReader(handle):
            erp.append(ErpOrder(
                order_id=line["order_id"],
                invoice_no=line["invoice_no"],
                gstin=line["gstin"].strip(),
                amount=paise(line["amount"]),
                invoice_date=date.fromisoformat(line["invoice_date"]),
            ))

    gstr2b = []
    with (root / "gstr2b.csv").open(newline="") as handle:
        for line in csv.DictReader(handle):
            gstr2b.append(Gstr2bLine(
                gstin=line["gstin"],
                invoice_no=line["invoice_no"],
                invoice_date=date.fromisoformat(line["invoice_date"]),
                taxable_value=paise(line["taxable_value"]),
                igst=paise(line["igst"]),
                cgst=paise(line["cgst"]),
                sgst=paise(line["sgst"]),
                irn=line["irn"],
                irn_generated_at=line["irn_generated_at"],
                gstr1_filing_period=line["gstr1_filing_period"],
                supplier_gstr3b_filed=line["supplier_gstr3b_filed"],
                itc_availability=line["itc_availability"],
            ))

    return Dataset(rows=rows, bank=bank, erp=erp, gstr2b=gstr2b, disputes=disputes)
