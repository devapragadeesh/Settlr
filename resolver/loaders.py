"""Read the SOLVER-VISIBLE artefacts of a dataset directory.

The file list is explicit and `ground_truth.json` is not on it. That is not
merely an omission: `FORBIDDEN` names it, and `load()` raises if a caller asks
for a directory whose contents it is not entitled to read. A rule expressed as
"we just do not open that file" is a rule that survives exactly until someone
needs a number quickly.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

#: Never opened by anything under `resolver/`.
FORBIDDEN = ("ground_truth.json",)


class GroundTruthAccess(Exception):
    """A resolver reached for the answer key."""


@dataclass(frozen=True, slots=True)
class BankLine:
    index: int
    reference: str
    value_date: date
    narration: str
    amount_paise: int

    @property
    def is_credit(self) -> bool:
        return self.amount_paise > 0


@dataclass(frozen=True, slots=True)
class Gstr2bLine:
    """One supplier invoice as the tax authority reports it.

    Field-identical to `matching/loaders.py`'s line of the same name, and
    DELIBERATELY not imported from it. `resolver/` shares no code with the
    frozen cascade -- `tests/test_isolation.py` forbids the import outright --
    because a resolver that reuses the engine it is being compared against is
    being compared with itself. The duplication is the price of that, and it is
    paid knowingly.

    This is `SourceSystem.TAX_AUTHORITY` data. `EvidenceKind.GST_DOCUMENT` is
    restricted by the contract to `Attests.ROW_EXISTENCE`: it can say an
    invoice exists, never which rows composed a bank credit. Nothing in this
    package may use it to license a composition.
    """

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


@dataclass
class Dataset:
    name: str
    rows: list[dict]
    bank: list[BankLine]
    #: `settlement_id -> {reported_reference, reported_amount, initiated_at}`.
    #: EMPTY when the PSP's settlement report does not exist -- a second
    #: gateway, a historical period, a bank feed held alone. Absence is a
    #: first-class state here, not a degenerate one.
    settlement_report: dict[str, dict] = field(default_factory=dict)
    erp_order_ids: frozenset[str] = frozenset()
    disputes: dict[str, dict] = field(default_factory=dict)
    #: GSTR-2B as filed by the merchant's suppliers. EMPTY where the merchant
    #: does not pull 2B, where the period predates e-invoicing, or where the
    #: feed is simply not shared with reconciliation. Absence is a first-class
    #: state here, not a degenerate one: it removes a tax FINDING and changes
    #: nothing about which rows settled, because GST evidence never licenses a
    #: composition in the first place.
    gstr2b: list[Gstr2bLine] = field(default_factory=list)

    @property
    def rows_carry_settlement_id(self) -> bool:
        """Does this feed carry a composition claim at all?

        Checked by KEY PRESENCE, not by truthiness: a null `settlement_id` says
        "this feed has settlement data and this row has none", an absent one
        says "this feed does not carry settlement data". They are different
        artefacts and only the second removes the claim.
        """
        return any("settlement_id" in row for row in self.rows)


def paise(text: str) -> int:
    """Rupee string -> integer paise, by string surgery. Never float."""
    text = (text or "0").strip()
    negative = text.startswith("-")
    whole, _, frac = text.lstrip("-").partition(".")
    value = int(whole or 0) * 100 + int((frac + "00")[:2])
    return -value if negative else value


def load(directory: Path) -> Dataset:
    directory = Path(directory)
    for name in FORBIDDEN:
        # The check is on INTENT, not on the filesystem: the key being absent
        # would make this pass for the wrong reason.
        if directory.name == name:
            raise GroundTruthAccess(name)

    rows = json.loads((directory / "recon_combined.json").read_text())["items"]

    bank: list[BankLine] = []
    with (directory / "bank_statement.csv").open(newline="") as handle:
        for index, line in enumerate(csv.DictReader(handle)):
            bank.append(BankLine(
                index=index,
                reference=line.get("bank_reference", "").strip(),
                value_date=date.fromisoformat(line["value_date"]),
                narration=line.get("narration", ""),
                amount_paise=paise(line["amount"])))

    report: dict[str, dict] = {}
    report_path = directory / "settlement_report.csv"
    if report_path.exists():
        with report_path.open(newline="") as handle:
            for line in csv.DictReader(handle):
                report[line["settlement_id"]] = {
                    "reported_reference": line.get("reported_reference", "").strip(),
                    "reported_amount": paise(line["reported_amount"]),
                    "initiated_at": line.get("initiated_at", ""),
                    "status": line.get("status", ""),
                }

    orders: set[str] = set()
    erp_path = directory / "erp_orders.csv"
    if erp_path.exists():
        with erp_path.open(newline="") as handle:
            orders = {line["order_id"] for line in csv.DictReader(handle)}

    disputes: dict[str, dict] = {}
    dispute_path = directory / "disputes.json"
    if dispute_path.exists():
        payload = json.loads(dispute_path.read_text())
        for item in payload.get("items", payload if isinstance(payload, list) else []):
            disputes[item.get("id") or item.get("dispute_id", "")] = item

    gstr2b: list[Gstr2bLine] = []
    gstr2b_path = directory / "gstr2b.csv"
    if gstr2b_path.exists():
        with gstr2b_path.open(newline="") as handle:
            for line in csv.DictReader(handle):
                gstr2b.append(Gstr2bLine(
                    gstin=line["gstin"].strip(),
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
                    itc_availability=line["itc_availability"]))

    return Dataset(name=directory.name, rows=rows, bank=bank,
                   settlement_report=report, erp_order_ids=frozenset(orders),
                   disputes=disputes, gstr2b=gstr2b)
