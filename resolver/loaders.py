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

    return Dataset(name=directory.name, rows=rows, bank=bank,
                   settlement_report=report, erp_order_ids=frozenset(orders),
                   disputes=disputes)
