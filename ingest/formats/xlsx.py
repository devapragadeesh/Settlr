"""`.xlsx` bank-statement adapter.

Scope, stated plainly: this reads ONE artifact -- `bank_statement.xlsx` -- into
the `bank` role only. It does not read `.xlsx` settlement reports, ERP order
books or GSTR-2B; those stay CSV/JSON. A bank feed is overwhelmingly the most
common real-world Excel input in this domain, and it is the one place the
repo's `_BANK_COLUMNS`/`resolve_role` role machinery already generalises
cleanly (`ingest/schema.py`).

**Money is integer paise everywhere (`CLAUDE.md`). No float arithmetic.**
openpyxl hands back a Python `float` for a numeric cell, and this module NEVER
multiplies that float by 100 -- `int(value * 100)` silently truncates on
values like `7612.99` that are not exactly representable in binary. Instead
every numeric cell is rendered to its exact two-decimal-place STRING via
`format(value, ".2f")` (correctly rounded, not truncated) and fed through the
existing `resolver.loaders.paise` grammar -- the same integer-arithmetic-on-a-
string path a CSV cell takes. A cell that is already text is passed to `paise`
unchanged.

Header-row detection: real exports carry preamble rows (account name, period,
opening balance) above the actual header. This scans the first
`MAX_PREAMBLE_ROWS` rows for the first one whose cells fully satisfy the bank
roles (`ingest/schema.py::BANK_ROLES`), via `ingest.schema.resolve_role`, and
treats it as the header. A file where no row in that window satisfies the
roles raises -- never silently guesses row 1.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import openpyxl

from ingest.normalize import build_bank_line
from ingest.schema import BANK_ROLES, resolve_role
from resolver.loaders import BankLine

MAX_PREAMBLE_ROWS = 20


def _cell_text(value: object) -> str:
    """Render one openpyxl cell to the string `paise`/`date.fromisoformat`
    expect -- never by float arithmetic."""
    if value is None:
        return ""
    if isinstance(value, (datetime.datetime, datetime.date)):
        d = value.date() if isinstance(value, datetime.datetime) else value
        return d.isoformat()
    if isinstance(value, float):
        return format(value, ".2f")
    return str(value)


def _find_header_row(rows: list[tuple]) -> tuple[int, tuple[str, ...]]:
    for row_index, row in enumerate(rows[:MAX_PREAMBLE_ROWS]):
        fieldnames = tuple(_cell_text(cell).strip() for cell in row)
        try:
            for role in BANK_ROLES:
                resolve_role(role, fieldnames)
        except ValueError:
            continue
        return row_index, fieldnames
    raise ValueError(
        f"no header row satisfying the bank roles found in the first "
        f"{MAX_PREAMBLE_ROWS} rows")


def load_bank_lines(path: Path) -> list[BankLine]:
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook.worksheets[0]
        rows = [row for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()

    header_index, fieldnames = _find_header_row(rows)
    ref_col = resolve_role(BANK_ROLES[0], fieldnames)
    date_col = resolve_role(BANK_ROLES[1], fieldnames)
    ref_i = fieldnames.index(ref_col)
    date_i = fieldnames.index(date_col)
    narration_i = fieldnames.index("narration") if "narration" in fieldnames else None
    amount_i = fieldnames.index("amount")

    bank: list[BankLine] = []
    index = 0
    for row in rows[header_index + 1:]:
        # A wholly blank row (common as a trailing spacer) carries no data at
        # all -- distinct from a row with an actually-empty reference cell,
        # which still has a value_date and amount and is not skipped.
        if all(cell is None for cell in row):
            continue
        bank.append(build_bank_line(
            index=index,
            reference=_cell_text(row[ref_i]),
            value_date_text=_cell_text(row[date_i]),
            narration=_cell_text(row[narration_i]) if narration_i is not None else "",
            amount_text=_cell_text(row[amount_i])))
        index += 1
    return bank
