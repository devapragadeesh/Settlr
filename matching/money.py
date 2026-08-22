"""Integer-paise money handling.

There is no float arithmetic in this package. Rupee strings appear only in the
bank statement and the ERP / GST companions; they are parsed by integer
arithmetic on the decimal string, never by `float()` or division.
"""

from __future__ import annotations

import re

_RUPEES = re.compile(r"^(-?)(\d+)(?:\.(\d{1,2}))?$")


def paise(rupee_string: str) -> int:
    """Parse a rupee string such as ``"1234.56"`` into integer paise.

    Rejects anything that is not a plain decimal with at most two places, so a
    malformed cell fails loudly rather than silently truncating.
    """
    match = _RUPEES.match(rupee_string.strip())
    if not match:
        raise ValueError(f"not a rupee amount: {rupee_string!r}")
    sign, whole, frac = match.groups()
    total = int(whole) * 100 + int((frac or "0").ljust(2, "0"))
    return -total if sign else total


def rupees(value: int) -> str:
    """Format integer paise back to a rupee string. Inverse of `paise`."""
    sign = "-" if value < 0 else ""
    whole, frac = divmod(abs(value), 100)
    return f"{sign}{whole}.{frac:02d}"


def inr(value: int) -> str:
    """Human-readable rupees with thousands separators, for reports."""
    sign = "-" if value < 0 else ""
    whole, frac = divmod(abs(value), 100)
    return f"{sign}₹{whole:,}.{frac:02d}"
