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
import re
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


#: A rupee cell is a plain decimal with at most two places. Anything else is a
#: malformed cell, and the only safe thing to do with a malformed money cell is
#: refuse it. This grammar is character-for-character the one `matching/money.py`
#: enforces; the two are duplicated rather than shared because `resolver/` may
#: not import `matching/` (`resolver/tests/test_isolation.py`'s FORBIDDEN set --
#: the frozen cascade must stay independently frozen). `test_malformed_bank.py::
#: test_the_two_paise_parsers_agree` pins them to the same behaviour so the
#: duplication cannot silently drift back apart.
_RUPEES = re.compile(r"^(-?)(\d+)(?:\.(\d{1,2}))?$")


def paise(text: str) -> int:
    """Rupee string -> integer paise, by integer arithmetic on the decimal
    string. Never float.

    Raises `ValueError` on anything that is not a plain decimal with at most
    two places, so a malformed cell fails loudly rather than silently losing
    precision. This parser previously did unchecked string surgery --
    `int((frac + "00")[:2])` -- which truncated `"7612.9951"` to `761299`
    paise with no signal, while `matching/money.py` raised on the identical
    cell. Two parsers for the same column disagreeing on what "more than two
    decimals" means is a correctness difference, not a crash difference, and
    the direction of the loss always favoured truncation.

    Verified behaviour-preserving on every dataset in the repository at the
    time of the change: 6,374 money cells across `bank_statement.csv`,
    `settlement_report.csv` and `gstr2b.csv` in all 168 dataset CSVs, zero of
    which this grammar rejects. No published figure moves.
    """
    match = _RUPEES.match((text or "").strip())
    if not match:
        raise ValueError(f"not a rupee amount: {text!r}")
    sign, whole, frac = match.groups()
    value = int(whole) * 100 + int((frac or "0").ljust(2, "0"))
    return -value if sign else value


def _load_disputes(path: Path) -> dict[str, dict]:
    """`disputes.json` -> `{dispute_id: item}`, refusing anything ambiguous.

    Three silent failures used to live in the two lines this replaces, all
    reported in `tests/adversarial/ADVERSARIAL_FINDINGS.md` and none of them
    fixed. Closed 2026-09-03; each raise below is one of them.

    1. **An unhandled top-level shape emptied the dispute set silently.** The
       old expression was
       `payload.get("items", payload if isinstance(payload, list) else [])`,
       so a `disputes.json` shaped as a plain JSON object -- neither
       `{"items": [...]}` nor a bare array -- fell through to `[]`. "No
       disputes exist" and "this file is a shape I do not understand" became
       indistinguishable. `matching/loaders.py:142` subscripts `["items"]`
       unconditionally and raises `KeyError` on the same file, so the two
       packages disagreed about a file they both read, and the resolver was
       the one that failed quietly.

    2. **An item with no usable identifier was stored under the key `""`.**
       `item.get("id") or item.get("dispute_id", "")` yields `""` when both
       are missing or empty. This never fires on the corpus, but it is the
       widest-blast-radius defect of the three, because of how the single
       consumer reads back: `resolver/breaks.py` looks up
       `disputes.get(row.get("dispute_id") or "")` -- so every payment row
       WITHOUT a `dispute_id` also probes key `""`. 94% of recon rows have no
       `dispute_id`. One malformed item would therefore have reclassified
       almost the entire non-disputed population as `UNEXPECTED_CHANGE` and
       routed it to disputes ops. Latent, not harmless.

    3. **A repeated id silently overwrote the earlier item**, dict-assignment
       being last-write-wins. Two disputes over one payment is a real-world
       shape; losing one without a signal is not an acceptable answer to it.

    Behaviour-preserving on every dataset in the repository, measured before
    the change rather than asserted after: 45 `disputes.json` files, 100%
    shaped `{"count", "entity", "items"}`, 5,472 items, **0** lacking both id
    keys and **0** duplicate ids. No published figure moves.

    `ValueError` rather than a package-defined type, matching `paise` above
    and `matching/money.py`: a corrupt input file is malformed data, not a
    contract violation. `ContractViolation` is for an outcome the contract
    forbids, and a resolver that has not run yet cannot have produced one.
    """
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
            f"'items'; found {found}. Refusing to treat an unrecognised "
            f"shape as an empty dispute set.")

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
                f"'dispute_id'. A dispute with no identifier cannot be "
                f"looked up, and keying it on '' would collide with every "
                f"row that has no dispute_id.")
        if key in disputes:
            raise ValueError(
                f"{path.name}: duplicate dispute id {key!r} at item "
                f"{position}; the earlier item would be discarded silently.")
        disputes[key] = item
    return disputes


#: `bank_statement.csv` ships under two column vocabularies in this repository
#: and they mean the same things. The corpus generator emits
#: `bank_reference,value_date`; the frozen `engine/generator.py` emitted
#: `utr,date`, and `engine/data`, `holdout/data` and every `scale/data_*`
#: fixture are frozen at that spelling and cannot be rewritten.
#:
#: Listed most-canonical-first. The value is a role, not a preference ordering
#: for merging: exactly one spelling of each role may appear in a given file.
_BANK_COLUMNS = {
    "reference": ("bank_reference", "utr"),
    "value_date": ("value_date", "date"),
}


def _bank_column(role: str, fieldnames: list[str] | None, path: Path) -> str:
    """Which spelling does this file use for `role`? Never guesses.

    The two loaders in this repository disagreed about `bank_statement.csv`'s
    header: `resolver/` read `bank_reference`/`value_date`, `matching/` read
    `utr`/`date`. Neither was wrong -- the corpus generator and the frozen
    `engine/generator.py` genuinely emit different spellings of the same two
    columns -- but the consequence was that `resolver.loaders.load` raised
    `KeyError: 'value_date'` on `engine/data`, `holdout/data` and all eight
    `scale/data_*` fixtures, so **the resolver could not read the held-out set
    or any throughput fixture at all.** That is the mechanical reason
    `investigation/BENCHMARK_EXTENSION_RESULTS.md` records resolver throughput
    at scale as unmeasured. Closed 2026-09-03.

    This accepts either spelling and refuses everything else. In particular it
    refuses a file carrying BOTH spellings of one role: two columns claiming
    the same meaning is a question about the data, and picking one would be
    the same silent guess as the three defects closed immediately before this.

    `matching/` is frozen and is not taught the second spelling; it reads the
    fixtures it was written for. This is a widening on the resolver side only.
    """
    present = [name for name in _BANK_COLUMNS[role] if name in (fieldnames or ())]
    if not present:
        accepted = " or ".join(repr(n) for n in _BANK_COLUMNS[role])
        raise ValueError(
            f"{path.name}: no {role} column -- expected {accepted}; "
            f"header is {list(fieldnames or [])!r}")
    if len(present) > 1:
        raise ValueError(
            f"{path.name}: ambiguous {role} column -- {present!r} both "
            f"present and they mean the same thing. Refusing to guess which "
            f"one is authoritative.")
    return present[0]


def load(directory: Path) -> Dataset:
    directory = Path(directory)
    for name in FORBIDDEN:
        # The check is on INTENT, not on the filesystem: the key being absent
        # would make this pass for the wrong reason.
        if directory.name == name:
            raise GroundTruthAccess(name)

    rows = json.loads((directory / "recon_combined.json").read_text())["items"]

    bank: list[BankLine] = []
    bank_path = directory / "bank_statement.csv"
    with bank_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        ref_col = _bank_column("reference", reader.fieldnames, bank_path)
        date_col = _bank_column("value_date", reader.fieldnames, bank_path)
        for index, line in enumerate(reader):
            bank.append(BankLine(
                index=index,
                reference=(line.get(ref_col) or "").strip(),
                value_date=date.fromisoformat(line[date_col]),
                narration=line.get("narration", ""),
                amount_paise=paise(line["amount"])))

    report: dict[str, dict] = {}
    report_path = directory / "settlement_report.csv"
    if report_path.exists():
        with report_path.open(newline="") as handle:
            for position, line in enumerate(csv.DictReader(handle)):
                settlement_id = line["settlement_id"]
                # Was last-write-wins, silently: a repeated settlement_id
                # discarded the earlier row with no signal. Closed 2026-09-03.
                # This feed is the PSP's ATTESTATION -- the evidence a
                # `Verified` composition is warranted by -- so dropping one of
                # two contradicting claims is the worst available answer;
                # noticing that the record contradicts itself is the whole
                # point of `AttestationDiscrepancy`. Behaviour-preserving:
                # 33 settlement_report.csv files, 512 rows, 0 duplicates.
                if settlement_id in report:
                    raise ValueError(
                        f"{report_path.name}: duplicate settlement_id "
                        f"{settlement_id!r} at row {position}; the earlier "
                        f"attestation would be discarded silently.")
                report[settlement_id] = {
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
        disputes = _load_disputes(dispute_path)

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
