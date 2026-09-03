"""SWIFT MT940 bank-statement adapter -- stdlib only, line-based.

Reads `:61:` statement lines (one bank movement each) and their associated
`:86:` narration continuation into `BankLine`s.

**`:61:` field grammar** (SWIFT standard, `6!n[4!n]2a[1!a]15d1!a3!c16x[//16x][34x]`):
value date (`YYMMDD`), optional entry date (`MMDD`), a debit/credit mark
(`C`/`D`; `RC`/`RD` reversal marks are read as `C`/`D`), an amount in
SWIFT's comma-decimal notation (`7612,99`), a transaction type code
(`NTRF` etc.), then a reference, optionally split by `//` into an owner
reference and a bank-assigned reference (the owner reference, before `//`,
is preferred -- it is the one a merchant's own systems assigned and is
therefore closer to `resolver.loaders`'s `reference` role than the bank's own
id would be).

**The century ambiguity, named rather than hidden.** `YYMMDD` carries no
century. This adapter applies the common SWIFT convention -- `00`-`79` ->
`20xx`, `80`-`99` -> `19xx` -- which is correct for every date in this
repository (2026-2028) but is a real, stated limitation: a genuinely
19xx-dated statement from a pre-2000 archive would be misread. No dataset in
this repo exercises that case, so it is disclosed rather than guarded by an
untestable branch.

**Fields discarded, named rather than silently dropped:** the funds code
(currency-change marker), the transaction type code itself (`NTRF` etc. --
kept nowhere, since `BankLine` has no field for it), the bank-assigned `//`
reference when an owner reference is present, and any `:86:` structured
subfield tags (`?20`, `?32`, ...) beyond treating the whole continuation as
one narration string.
"""

from __future__ import annotations

import re
from pathlib import Path

from ingest.normalize import build_bank_line
from resolver.loaders import BankLine

_LINE_61 = re.compile(
    r"^:61:"
    r"(?P<value_date>\d{6})"
    r"(?:\d{4})?"                     # optional entry date, discarded
    r"(?P<mark>R?[CD])"
    r"(?:[A-Z])?"                     # optional funds code, discarded
    r"(?P<amount>\d+,\d*)"
    r"(?P<type>[A-Z0-9]{4})"
    r"(?P<ref>.*)$"
)


def _year(yy: int) -> int:
    return 2000 + yy if yy <= 79 else 1900 + yy


def _value_date_iso(value_date: str) -> str:
    yy, mm, dd = int(value_date[0:2]), int(value_date[2:4]), int(value_date[4:6])
    return f"{_year(yy):04d}-{mm:02d}-{dd:02d}"


def _reference(ref_field: str) -> str:
    owner, _, _bank_ref = ref_field.partition("//")
    return owner.strip()


def load_bank_lines(path: Path) -> list[BankLine]:
    lines = Path(path).read_text().splitlines()

    entries: list[tuple[re.Match, str]] = []
    for raw_line in lines:
        if raw_line.startswith(":61:"):
            match = _LINE_61.match(raw_line)
            if not match:
                raise ValueError(f"malformed :61: statement line: {raw_line!r}")
            entries.append((match, ""))
            continue
        if raw_line.startswith(":86:") and entries:
            match_i, _ = entries[-1]
            entries[-1] = (match_i, raw_line[len(":86:"):])

    bank: list[BankLine] = []
    for index, (match, narration) in enumerate(entries):
        mark = match.group("mark").lstrip("R")
        if mark not in ("C", "D"):
            raise ValueError(f"unrecognised debit/credit mark: {match.group('mark')!r}")
        amount_text = match.group("amount").replace(",", ".")
        if amount_text.endswith("."):
            amount_text += "0"
        signed = amount_text if mark == "C" else f"-{amount_text}"
        bank.append(build_bank_line(
            index=index,
            reference=_reference(match.group("ref")),
            value_date_text=_value_date_iso(match.group("value_date")),
            narration=narration,
            amount_text=signed))
    return bank
