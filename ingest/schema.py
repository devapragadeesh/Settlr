"""The role vocabulary: what a `Dataset` needs, independent of what format it
arrives in.

This is the reversal of `DECISIONS.md` Sec.72, which rejected a general
header-normalisation layer on the grounds that "there are exactly two
spellings of exactly two columns in one file" -- a mapping layer at that point
would have been "a new surface with no second consumer". Adding `.xlsx`,
CAMT.053 and MT940 (Phases A2/A3) is that second consumer. Sec.72's other two
rules are kept unchanged here, generalised rather than discarded:

* two spellings of one role present in the same source is a `ValueError`,
  never resolved by preference order (`resolve_role` below);
* no frozen dataset is ever rewritten to suit a reader.

A role is a MEANING (`bank.reference`), not a column name. Every format
adapter's job is to emit values keyed by role; `ingest/normalize.py` is the
one place that turns roles into a `resolver.loaders.Dataset`. Every format
therefore converges before it can diverge -- a defect in the CAMT adapter and
a defect in the CSV adapter cannot silently drift into inconsistent
`Dataset` shapes, because there is only one place that builds one.
"""

from __future__ import annotations

from dataclasses import dataclass

from resolver_contract.types import SourceSystem


@dataclass(frozen=True, slots=True)
class Role:
    """One field this repo's `Dataset` needs, and where it may come from."""

    name: str
    source: SourceSystem
    #: Accepted spellings, canonical form first. Order is NOT a merge
    #: preference -- `resolve_role` raises if more than one is present.
    spellings: tuple[str, ...]
    required: bool


#: `bank_statement.csv` / CAMT.053 / MT940 roles. Generalises
#: `resolver/loaders.py:_BANK_COLUMNS`. `SourceSystem.BANK` is threaded
#: through every adapter that populates these, which is what keeps the
#: independence accounting in `resolver_contract/types.py::SOURCE_PARTY`
#: correct regardless of which format the bytes arrived in.
BANK_ROLES = (
    Role("reference", SourceSystem.BANK, ("bank_reference", "utr"), required=True),
    Role("value_date", SourceSystem.BANK, ("value_date", "date"), required=True),
    Role("narration", SourceSystem.BANK, ("narration",), required=False),
    Role("amount", SourceSystem.BANK, ("amount",), required=True),
)

#: `settlement_report.csv` roles -- the PSP's own settlement report, a
#: distinct artefact from `recon_combined.json` (Sec.24) though the same
#: party.
SETTLEMENT_REPORT_ROLES = (
    Role("settlement_id", SourceSystem.PSP_SETTLEMENT_REPORT, ("settlement_id",), required=True),
    Role("reported_reference", SourceSystem.PSP_SETTLEMENT_REPORT, ("reported_reference",), required=False),
    Role("reported_amount", SourceSystem.PSP_SETTLEMENT_REPORT, ("reported_amount",), required=True),
    Role("initiated_at", SourceSystem.PSP_SETTLEMENT_REPORT, ("initiated_at",), required=False),
    Role("status", SourceSystem.PSP_SETTLEMENT_REPORT, ("status",), required=False),
)

#: `erp_orders.csv` roles -- `resolver/loaders.py` keeps only `order_id`
#: today (a `frozenset[str]`); the role exists so a richer adapter has
#: somewhere to converge without widening what `resolver.loaders` itself
#: reads.
ERP_ROLES = (
    Role("order_id", SourceSystem.MERCHANT_ERP, ("order_id",), required=True),
)

#: `gstr2b.csv` roles, all 12 columns of `resolver.loaders.Gstr2bLine`.
GSTR2B_ROLES = (
    Role("gstin", SourceSystem.TAX_AUTHORITY, ("gstin",), required=True),
    Role("invoice_no", SourceSystem.TAX_AUTHORITY, ("invoice_no",), required=True),
    Role("invoice_date", SourceSystem.TAX_AUTHORITY, ("invoice_date",), required=True),
    Role("taxable_value", SourceSystem.TAX_AUTHORITY, ("taxable_value",), required=True),
    Role("igst", SourceSystem.TAX_AUTHORITY, ("igst",), required=True),
    Role("cgst", SourceSystem.TAX_AUTHORITY, ("cgst",), required=True),
    Role("sgst", SourceSystem.TAX_AUTHORITY, ("sgst",), required=True),
    Role("irn", SourceSystem.TAX_AUTHORITY, ("irn",), required=True),
    Role("irn_generated_at", SourceSystem.TAX_AUTHORITY, ("irn_generated_at",), required=True),
    Role("gstr1_filing_period", SourceSystem.TAX_AUTHORITY, ("gstr1_filing_period",), required=True),
    Role("supplier_gstr3b_filed", SourceSystem.TAX_AUTHORITY, ("supplier_gstr3b_filed",), required=True),
    Role("itc_availability", SourceSystem.TAX_AUTHORITY, ("itc_availability",), required=True),
)


class RoleConflict(ValueError):
    """More than one spelling for the same role appeared in one source."""


class RoleMissing(ValueError):
    """A required role had no spelling present in the source."""


def resolve_role(role: Role, fieldnames: tuple[str, ...]) -> str | None:
    """Which literal column name satisfies `role`, or `None` if optional and absent.

    Direct generalisation of `resolver/loaders.py::_bank_column`: never
    guesses, never prefers one spelling over another when both are present.
    """
    present = [name for name in role.spellings if name in fieldnames]
    if not present:
        if role.required:
            raise RoleMissing(
                f"no column for role {role.name!r}; looked for "
                f"{role.spellings!r} in {fieldnames!r}")
        return None
    if len(present) > 1:
        raise RoleConflict(
            f"role {role.name!r} has {len(present)} spellings present at "
            f"once: {present!r} -- exactly one meaning must be sent")
    return present[0]
