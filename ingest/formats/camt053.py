"""ISO 20022 CAMT.053 bank-statement adapter -- stdlib only.

Reads `<Ntry>` elements into `BankLine`s: `Amt`+`Ccy`, `CdtDbtInd` (CRDT/DBIT
sign), `BookgDt`/`ValDt` (value date preferred, falling back to booking date),
`NtryRef` (falling back to `AcctSvcrRef`) as the reference, `AddtlNtryInf` as
narration.

**Untrusted input over a network transport (Track B) means XXE is a real
threat, not a theoretical one, and it is refused before parsing, not
sanitised after.** Python's `xml.etree.ElementTree` does not resolve external
entities by default, but it IS vulnerable to internal entity expansion
("billion laughs") -- a small file that expands to gigabytes in memory. This
module refuses to parse any document containing a `<!DOCTYPE` declaration at
all: a CAMT.053 statement legitimately never carries one, so this is not a
narrowing of what a real bank feed looks like, and it removes the entity
machinery's on-ramp entirely rather than trying to allow-list safe entities.
`ingest/tests/test_camt053.py::test_a_doctype_declaration_is_refused_before_parsing`
proves this with a real billion-laughs payload and asserts it never reaches
the XML parser.

**Fields this format carries that `BankLine` discards, named rather than
silently dropped:** `Ccy` (currency code -- this repo assumes INR throughout
and has no field for a second currency), `CdtDbtInd` as a standalone flag (the
sign is folded into `amount_paise` instead, matching the existing convention),
any `Ustrd`/structured remittance breakdown beyond the first `AddtlNtryInf`
string, and every non-`Ntry` statement-level field (`GrpHdr`, `Bal`, account
identifiers).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ingest.normalize import build_bank_line
from resolver.loaders import BankLine

# Namespace-agnostic: CAMT.053 ships under several near-identical namespace
# URIs across bank vendors and schema versions (e.g.
# urn:iso:std:iso:20022:tech:xsd:camt.053.001.02 vs .001.08). Matching on the
# LOCAL tag name rather than a fully-qualified name avoids hardcoding one
# version and silently refusing every other.


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in element.iter():
        if _local(child.tag) == local_name:
            return child
    return None


def _find_direct(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in element:
        if _local(child.tag) == local_name:
            return child
    return None


def _entry_amount_text(entry: ET.Element) -> tuple[str, str]:
    amt_element = _find_direct(entry, "Amt")
    if amt_element is None or amt_element.text is None:
        raise ValueError("entry has no <Amt>")
    sign_element = _find_direct(entry, "CdtDbtInd")
    sign = (sign_element.text or "").strip().upper() if sign_element is not None else ""
    if sign not in ("CRDT", "DBIT"):
        raise ValueError(f"entry has no valid <CdtDbtInd>: {sign!r}")
    text = amt_element.text.strip()
    return (f"-{text}" if sign == "DBIT" and not text.startswith("-") else text), sign


def _entry_reference(entry: ET.Element) -> str:
    ref = _find(entry, "NtryRef")
    if ref is not None and ref.text:
        return ref.text.strip()
    acct_ref = _find(entry, "AcctSvcrRef")
    if acct_ref is not None and acct_ref.text:
        return acct_ref.text.strip()
    return ""


def _entry_value_date(entry: ET.Element) -> str:
    for wrapper_name in ("ValDt", "BookgDt"):
        wrapper = _find_direct(entry, wrapper_name)
        if wrapper is not None:
            dt = _find_direct(wrapper, "Dt")
            if dt is not None and dt.text:
                return dt.text.strip()
    raise ValueError("entry has no <ValDt>/<BookgDt><Dt>")


def _entry_narration(entry: ET.Element) -> str:
    # Not `.strip()`ed: `resolver.loaders`'s CSV/JSON reader never strips
    # narration either (`line.get("narration", "")`), and a few real
    # narration strings in this repo's own datasets carry a trailing space
    # that a round-trip test would otherwise lose.
    info = _find(entry, "AddtlNtryInf")
    return (info.text or "") if info is not None else ""


def load_bank_lines(path: Path) -> list[BankLine]:
    raw = Path(path).read_text()
    if "<!DOCTYPE" in raw.upper().replace(" ", ""):
        raise ValueError(
            "refusing to parse: document declares a DOCTYPE, which a "
            "CAMT.053 statement never legitimately needs and which is the "
            "on-ramp for XML entity-expansion attacks")

    root = ET.fromstring(raw)
    entries = [element for element in root.iter() if _local(element.tag) == "Ntry"]

    bank: list[BankLine] = []
    for index, entry in enumerate(entries):
        amount_text, _sign = _entry_amount_text(entry)
        bank.append(build_bank_line(
            index=index,
            reference=_entry_reference(entry),
            value_date_text=_entry_value_date(entry),
            narration=_entry_narration(entry),
            amount_text=amount_text))
    return bank
