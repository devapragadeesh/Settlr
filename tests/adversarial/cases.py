"""The corruption registry.

Every `Case` is a single-field or single-file mutation of the baseline
dataset built by `conftest.py`. `mutate(dataset_dir)` corrupts the clone in
place and returns a small metadata dict describing what it touched, which the
`_survives` test files and `run_adversarial.py` use to scope the bucket-3
check to the thing actually corrupted rather than the whole dataset.

`target_bank_index` is `0` for every case that corrupts the first attested
settlement (`setl_3XDSdIhVtpYs2i`, reference `RATN27006653315`, bank line 0
in the baseline) -- fixed and known ahead of time because the baseline is
frozen. It is `None` for cases that corrupt dataset-wide structure (a missing
`items` key, a zero-row file, ...), where the check instead asks whether
*any* line came back confidently positive out of a file that should not have
produced one.

This module defines no tests itself -- nothing here is collected by pytest.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

Mutator = Callable[[Path], dict]


@dataclass(frozen=True)
class Case:
    name: str
    surface: str                       # recon | bank | settlement_report | erp | disputes
    mutate: Mutator
    targets: frozenset[str] = frozenset({"resolver", "matching"})
    note: str = ""


# ---------------------------------------------------------------------------
# small file helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    return json.loads(path.read_text())


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1))


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames), list(reader)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _date_and_ref_columns(fieldnames: list[str]) -> tuple[str, str]:
    """Bank files carry different column names in each package's shape --
    `value_date`/`bank_reference` (resolver) or `date`/`utr` (matching)."""
    date_col = "date" if "date" in fieldnames else "value_date"
    ref_col = "utr" if "utr" in fieldnames else "bank_reference"
    return date_col, ref_col


# ---------------------------------------------------------------------------
# recon_combined.json
# ---------------------------------------------------------------------------

def _truncated_json(directory: Path) -> dict:
    path = directory / "recon_combined.json"
    text = path.read_text()
    path.write_text(text[: len(text) // 2])
    return {"target_bank_index": None}


def _missing_items_key(directory: Path) -> dict:
    path = directory / "recon_combined.json"
    data = _read_json(path)
    del data["items"]
    _write_json(path, data)
    return {"target_bank_index": None}


def _empty_items_array(directory: Path) -> dict:
    path = directory / "recon_combined.json"
    data = _read_json(path)
    data["items"] = []
    data["count"] = 0
    _write_json(path, data)
    return {"target_bank_index": None}


def _duplicate_entity_id(directory: Path) -> dict:
    path = directory / "recon_combined.json"
    data = _read_json(path)
    first = data["items"][0]
    clone = dict(first)
    # a second row claiming the SAME entity_id but a different amount --
    # a duplicate primary key, not merely a repeated row.
    clone["credit"] = (clone.get("credit") or 0) + 100
    data["items"].insert(1, clone)
    _write_json(path, data)
    return {"target_bank_index": 0}


def _negative_amount(directory: Path) -> dict:
    path = directory / "recon_combined.json"
    data = _read_json(path)
    data["items"][0]["credit"] = -data["items"][0]["credit"]
    _write_json(path, data)
    return {"target_bank_index": 0}


def _out_of_order_created_at(directory: Path) -> dict:
    path = directory / "recon_combined.json"
    data = _read_json(path)
    items = data["items"]
    items[0]["created_at"], items[-1]["created_at"] = (
        items[-1]["created_at"], items[0]["created_at"])
    _write_json(path, data)
    return {"target_bank_index": 0}


def _settlement_id_null(directory: Path) -> dict:
    path = directory / "recon_combined.json"
    data = _read_json(path)
    for item in data["items"]:
        if item.get("settlement_id") == "setl_3XDSdIhVtpYs2i":
            item["settlement_id"] = None
    _write_json(path, data)
    return {"target_bank_index": 0}


# resolver-only: nulling settlement_id on one row of the batch drops it out
# of `by_settlement` (grouped by KEY PRESENCE), so the attested composition
# resolver sees is now short one row and its residual should no longer
# close -- a real, meaningful test of Tier A/B. `matching`'s Stage 3 pool is
# BLIND to settlement_id entirely (it reconstructs by amount alone, with
# "the settlement columns... withheld from the enumerator" -- see
# `matching/cascade.py`'s own module docstring): the row stays in the pool
# regardless, and the solver still finds the true, CORRECT closing subset.
# A Determinate there is the right answer arrived at by a path this field
# never touches, not a corrupted one -- confirmed by running the case and
# inspecting `matching`'s output before deciding this, not assumed.
_SETTLEMENT_ID_NULL_TARGETS = frozenset({"resolver"})


def _settlement_id_absent(directory: Path) -> dict:
    path = directory / "recon_combined.json"
    data = _read_json(path)
    for item in data["items"]:
        if item.get("settlement_id") == "setl_3XDSdIhVtpYs2i":
            del item["settlement_id"]
    _write_json(path, data)
    return {"target_bank_index": 0}


def _non_numeric_amount(directory: Path) -> dict:
    path = directory / "recon_combined.json"
    data = _read_json(path)
    data["items"][0]["credit"] = "not-a-number"
    _write_json(path, data)
    return {"target_bank_index": 0}


def _over_precision_amount(directory: Path) -> dict:
    """`credit`/`amount` in recon_combined.json are already integer paise, so
    "over-precision" here means injecting a float where the whole codebase's
    invariant ("money is integer paise everywhere") assumes an int -- the
    JSON-side analogue of the CSV over-precision case in test_malformed_bank.
    """
    path = directory / "recon_combined.json"
    data = _read_json(path)
    data["items"][0]["credit"] = data["items"][0]["credit"] + 0.126
    _write_json(path, data)
    return {"target_bank_index": 0}


RECON_CASES = [
    Case("truncated_json", "recon", _truncated_json),
    Case("missing_items_key", "recon", _missing_items_key),
    Case("empty_items_array", "recon", _empty_items_array),
    Case("duplicate_entity_id", "recon", _duplicate_entity_id),
    Case("negative_amount", "recon", _negative_amount),
    Case("out_of_order_created_at", "recon", _out_of_order_created_at),
    Case("settlement_id_null", "recon", _settlement_id_null,
         targets=_SETTLEMENT_ID_NULL_TARGETS),
    Case("settlement_id_absent", "recon", _settlement_id_absent),
    Case("non_numeric_amount", "recon", _non_numeric_amount),
    Case("over_precision_amount", "recon", _over_precision_amount),
]


# ---------------------------------------------------------------------------
# bank_statement.csv
# ---------------------------------------------------------------------------

def _missing_header_column(directory: Path) -> dict:
    path = directory / "bank_statement.csv"
    fieldnames, rows = _read_csv(path)
    date_col, _ = _date_and_ref_columns(fieldnames)
    kept = [c for c in fieldnames if c != date_col]
    for row in rows:
        row.pop(date_col, None)
    _write_csv(path, kept, rows)
    return {"target_bank_index": None}


def _blank_value_date(directory: Path) -> dict:
    path = directory / "bank_statement.csv"
    fieldnames, rows = _read_csv(path)
    date_col, _ = _date_and_ref_columns(fieldnames)
    rows[0][date_col] = ""
    _write_csv(path, fieldnames, rows)
    return {"target_bank_index": 0}


def _non_numeric_bank_amount(directory: Path) -> dict:
    path = directory / "bank_statement.csv"
    fieldnames, rows = _read_csv(path)
    rows[0]["amount"] = "not-a-number"
    _write_csv(path, fieldnames, rows)
    return {"target_bank_index": 0}


def _duplicate_bank_reference(directory: Path) -> dict:
    """Inserts a SECOND, brand-new line (a clone of line 0) carrying the same
    reference -- `rows.insert(1, clone)` shifts every later line down by one,
    but line 0 itself is untouched. The interesting question is whether that
    NEW line (now index 1) gets independently resolved/verified against the
    same settlement a second time (double-booking); line 0 resolving exactly
    as it always did is the expected, correct, UNcorrupted answer and must
    not be the thing checked."""
    path = directory / "bank_statement.csv"
    fieldnames, rows = _read_csv(path)
    _, ref_col = _date_and_ref_columns(fieldnames)
    clone = dict(rows[0])
    rows.insert(1, clone)
    _write_csv(path, fieldnames, rows)
    return {"target_bank_index": 1}


def _zero_row_bank_file(directory: Path) -> dict:
    path = directory / "bank_statement.csv"
    fieldnames, _ = _read_csv(path)
    _write_csv(path, fieldnames, [])
    return {"target_bank_index": None}


def _only_foreign_lines(directory: Path) -> dict:
    """Every credit reference is replaced with one that names no settlement
    this dataset's PSP-side artefacts (recon rows, settlement_report) claim.

    Checked, not assumed: `target_bank_index` is `"n/a"`, NOT `None`. Both
    packages route a settlement to its bank line by AMOUNT (+date), not by
    string-matching the reference, once the reference-based shortcut fails --
    that is documented, intentional design, not an oversight: resolver's own
    module docstring names Tier B ("the link from batch to line rests on the
    amount alone") and the frozen cascade's Stage 2 is an "(amount, date)
    fallback for broken join keys" (`CLAUDE.md`). This mutation changes
    nothing about amount or date, so every settlement still correlates to
    exactly the one bank line it always did, and both packages correctly
    recover the TRUE composition despite the garbled reference -- that was
    confirmed by running this case before writing this comment, not assumed:
    a first version of this suite scored that as bucket 3 and was wrong to.
    A reference string alone carries no evidentiary weight either package's
    Tier-B/Stage-3 arithmetic depends on, so no bucket-3 check applies to it.
    """
    path = directory / "bank_statement.csv"
    fieldnames, rows = _read_csv(path)
    _, ref_col = _date_and_ref_columns(fieldnames)
    for index, row in enumerate(rows):
        row[ref_col] = f"FOREIGNREF{index:04d}"
    _write_csv(path, fieldnames, rows)
    return {"target_bank_index": "n/a"}


def _over_precision_bank_amount(directory: Path) -> dict:
    """More than two decimal digits on the bank's own amount column.

    This case originally documented a divergence: `matching/money.paise`
    rejected the cell and `resolver/loaders.paise` silently truncated it to
    the first two decimal digits, so `"7612.9951"` and the baseline's true
    `"7612.99"` both became 761299 paise. A `Verified` here was therefore the
    numerically CORRECT answer reached by a code path that happened not to
    validate precision -- which is why the outcome could not honestly be
    scored right or wrong, and the definitive finding lived in the
    function-level comparison instead.

    Fixed 2026-09-03: both parsers now enforce the same grammar and reject
    the cell, so this case is expected to raise `ValueError` out of the
    loader on BOTH packages (bucket 2). The direct comparison is
    `test_malformed_bank.py::test_the_two_paise_parsers_agree`.
    """
    path = directory / "bank_statement.csv"
    fieldnames, rows = _read_csv(path)
    rows[0]["amount"] = "7612.9951"
    _write_csv(path, fieldnames, rows)
    return {"target_bank_index": "n/a"}


BANK_CASES = [
    Case("missing_header_column", "bank", _missing_header_column),
    Case("blank_value_date", "bank", _blank_value_date),
    Case("non_numeric_amount", "bank", _non_numeric_bank_amount),
    Case("duplicate_bank_reference", "bank", _duplicate_bank_reference),
    Case("zero_row_file", "bank", _zero_row_bank_file),
    Case("only_foreign_lines", "bank", _only_foreign_lines),
    Case("over_precision_amount", "bank", _over_precision_bank_amount),
]


# ---------------------------------------------------------------------------
# settlement_report.csv (resolver only -- matching never reads this file)
# ---------------------------------------------------------------------------

def _duplicate_settlement_id_report(directory: Path) -> dict:
    path = directory / "settlement_report.csv"
    fieldnames, rows = _read_csv(path)
    first = dict(rows[0])
    # a SECOND row for the same settlement_id, a different reported_amount --
    # last-write-wins is the thing under test.
    first["reported_amount"] = "1.00"
    rows.append(first)
    _write_csv(path, fieldnames, rows)
    return {"target_bank_index": 0}


def _missing_reported_amount_column(directory: Path) -> dict:
    path = directory / "settlement_report.csv"
    fieldnames, rows = _read_csv(path)
    kept = [c for c in fieldnames if c != "reported_amount"]
    for row in rows:
        row.pop("reported_amount", None)
    _write_csv(path, kept, rows)
    return {"target_bank_index": None}


def _non_numeric_report_amount(directory: Path) -> dict:
    path = directory / "settlement_report.csv"
    fieldnames, rows = _read_csv(path)
    rows[0]["reported_amount"] = "not-a-number"
    _write_csv(path, fieldnames, rows)
    return {"target_bank_index": 0}


SETTLEMENT_REPORT_CASES = [
    Case("duplicate_settlement_id", "settlement_report",
         _duplicate_settlement_id_report, targets=frozenset({"resolver"})),
    Case("missing_reported_amount_column", "settlement_report",
         _missing_reported_amount_column, targets=frozenset({"resolver"})),
    Case("non_numeric_amount", "settlement_report",
         _non_numeric_report_amount, targets=frozenset({"resolver"})),
]


# ---------------------------------------------------------------------------
# erp_orders.csv / disputes.json
# ---------------------------------------------------------------------------

def _malformed_disputes_shape(directory: Path) -> dict:
    """`resolver.loaders.load` handles a bare array OR `{"items": [...]}`
    (`payload.get("items", payload if isinstance(payload, list) else [])`).
    `matching.loaders.load` handles ONLY `{"items": [...]}`
    (`json.loads(...)["items"]`, no fallback). The shape neither handles is a
    JSON OBJECT that is not `{"items": [...]}` -- e.g. a bare mapping keyed
    by dispute id. That is what this case writes."""
    path = directory / "disputes.json"
    data = _read_json(path)
    items = data.get("items", data if isinstance(data, list) else [])
    keyed = {item.get("id", f"disp_{i}"): item for i, item in enumerate(items)}
    _write_json(path, keyed)
    # "n/a": disputes.json never feeds Verified/Determinate arithmetic in
    # either package (matching's stage4 reads `dispute_id` off the RECON
    # rows, never off `dataset.disputes`; resolver's composition tiers never
    # touch it at all) -- confirmed by running this case and finding
    # Verified/Determinate counts identical to the uncorrupted baseline, not
    # assumed. A confident answer elsewhere in an unrelated dataset says
    # nothing about whether THIS file's corruption was noticed; see
    # `test_malformed_erp_disputes.py` for the check that actually exercises
    # what this corruption touches (`dataset.disputes` itself).
    return {"target_bank_index": "n/a"}


def _dispute_missing_id(directory: Path) -> dict:
    path = directory / "disputes.json"
    data = _read_json(path)
    items = data.get("items", data if isinstance(data, list) else [])
    if items:
        items[0].pop("id", None)
        items[0].pop("dispute_id", None)
    if isinstance(data, dict):
        data["items"] = items
        _write_json(path, data)
    else:
        _write_json(path, items)
    # "n/a" for the same reason as `_malformed_disputes_shape` above:
    # disputes.json content never reaches Verified/Determinate arithmetic.
    return {"target_bank_index": "n/a"}


DISPUTES_CASES = [
    Case("malformed_shape", "disputes", _malformed_disputes_shape),
    Case("missing_id", "disputes", _dispute_missing_id),
]

ALL_CASES = (RECON_CASES + BANK_CASES + SETTLEMENT_REPORT_CASES
             + DISPUTES_CASES)
