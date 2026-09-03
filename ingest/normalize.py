"""Role-keyed staging records -> `resolver.loaders.Dataset`.

The one canonical builder every format adapter converges on (Sec.79's module
docstring). A defect in a CAMT.053 adapter and a defect in a CSV adapter
cannot silently diverge into different `Dataset` shapes, because both must
produce the same staging shape this module consumes.

Every builder here reuses `resolver.loaders.paise` for money and the stdlib
`date.fromisoformat` for dates -- never a re-implementation of either, per
Sec.70's rule against two parsers for one column.
"""

from __future__ import annotations

from datetime import date

from resolver.loaders import BankLine, Dataset, Gstr2bLine, paise


def build_bank_line(index: int, reference: str, value_date_text: str,
                     narration: str, amount_text: str) -> BankLine:
    return BankLine(
        index=index,
        reference=(reference or "").strip(),
        value_date=date.fromisoformat(value_date_text),
        narration=narration or "",
        amount_paise=paise(amount_text))


def build_settlement_entry(reported_reference: str, reported_amount_text: str,
                            initiated_at: str, status: str) -> dict:
    return {
        "reported_reference": (reported_reference or "").strip(),
        "reported_amount": paise(reported_amount_text),
        "initiated_at": initiated_at or "",
        "status": status or "",
    }


def build_gstr2b_line(*, gstin: str, invoice_no: str, invoice_date_text: str,
                       taxable_value_text: str, igst_text: str, cgst_text: str,
                       sgst_text: str, irn: str, irn_generated_at: str,
                       gstr1_filing_period: str, supplier_gstr3b_filed: str,
                       itc_availability: str) -> Gstr2bLine:
    return Gstr2bLine(
        gstin=gstin.strip(),
        invoice_no=invoice_no,
        invoice_date=date.fromisoformat(invoice_date_text),
        taxable_value=paise(taxable_value_text),
        igst=paise(igst_text),
        cgst=paise(cgst_text),
        sgst=paise(sgst_text),
        irn=irn,
        irn_generated_at=irn_generated_at,
        gstr1_filing_period=gstr1_filing_period,
        supplier_gstr3b_filed=supplier_gstr3b_filed,
        itc_availability=itc_availability)


def build_dataset(*, name: str, rows: list[dict], bank: list[BankLine],
                   settlement_report: dict[str, dict],
                   erp_order_ids: frozenset[str],
                   disputes: dict[str, dict],
                   gstr2b: list[Gstr2bLine]) -> Dataset:
    return Dataset(name=name, rows=rows, bank=bank,
                    settlement_report=settlement_report,
                    erp_order_ids=erp_order_ids, disputes=disputes,
                    gstr2b=gstr2b)
