"""Stage 4 -- exception routing.

Every row the cascade did not match ends here, and the job is to say WHY in a
way that distinguishes root causes a controller would act on differently.
Collapsing them into one "unmatched" bucket is a precision failure: a payment
that will settle next Tuesday and a chargeback debit that can never be joined
are both "unmatched" and share nothing else.

Three of these are NOT exceptions at all -- `subset_sum_rolled_forward`,
`not_yet_eligible` and `netted_out_by_full_refund` are correct, expected
states. They are classified and reported so that they are visibly ACCOUNTED
FOR rather than quietly inflating either the match rate or the exception queue.

`type` and `owner` are assigned by rules. The LLM sees them only afterwards,
and only to phrase them. See `matching/llm.py`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .loaders import (
    Dataset, Gstr2bLine, is_failed, is_unjoinable_adjustment, to_date,
)
from .llm import ExplanationRequest, Explainer, get_explainer
from .money import inr, rupees
from .stage2_fuzzy import TOLERANCE_PAISE_PER_ROW
from .stage3_solver import Stage3Result, eligible_from

#: Confidence is a stated scale, not a vibe:
#:   1.00  read directly off an explicit field (on_hold, fee is null)
#:   0.90  derived by arithmetic over the ledger (refunds cancel a payment)
#:   0.75  inferred from an ABSENCE (no ERP order exists) -- absence is weaker
#:         evidence than presence because it cannot distinguish "missing" from
#:         "never existed"
CONFIDENCE_EXPLICIT = 1.00
CONFIDENCE_DERIVED = 0.90
CONFIDENCE_FROM_ABSENCE = 0.75

OWNERS = {
    "subset_sum_rolled_forward": "no-action",
    "not_yet_eligible": "no-action",
    "netted_out_by_full_refund": "no-action",
    "failed_payment_never_settles": "no-action",
    "deferred_debit_pending": "treasury",
    "dispute_hold_pending": "disputes-ops",
    "lost_dispute_adjustment": "finance-ops",
    "erp_gap_no_order": "finance-ops",
    "erp_gap_no_payment": "finance-ops",
    "gstr2b_absent": "tax-ops",
    "gstr2b_no_irn": "tax-ops",
    "gstr2b_37a_exposure": "tax-ops",
    "ambiguous_batch_membership": "finance-ops",
    "genuinely_unresolved": "finance-ops",
}

#: Types that are correct, expected states rather than problems.
NOT_A_PROBLEM = frozenset({
    "subset_sum_rolled_forward", "not_yet_eligible",
    "netted_out_by_full_refund", "failed_payment_never_settles",
})


@dataclass(frozen=True, slots=True)
class Exception_:
    type: str
    entity_id: str
    evidence: dict
    proposed_je: str | None
    confidence: float
    owner: str
    narrative: str = ""

    @property
    def is_actionable(self) -> bool:
        return self.type not in NOT_A_PROBLEM


@dataclass
class TaxFindings:
    supplier_gstin: str | None = None
    monthly_accrual: dict[str, tuple[int, int]] = field(default_factory=dict)
    fee_charged_without_gst_paise: int = 0
    fee_without_gst_rows: list[str] = field(default_factory=list)
    rounding_residuals: list[dict] = field(default_factory=list)
    itc_at_risk_paise: int = 0
    itc_lines: list[dict] = field(default_factory=list)


@dataclass
class Stage4Result:
    exceptions: list[Exception_] = field(default_factory=list)
    tax: TaxFindings = field(default_factory=TaxFindings)

    def by_type(self) -> dict[str, list[Exception_]]:
        grouped: dict[str, list[Exception_]] = defaultdict(list)
        for item in self.exceptions:
            grouped[item.type].append(item)
        return dict(sorted(grouped.items()))

    @property
    def actionable(self) -> list[Exception_]:
        return [item for item in self.exceptions if item.is_actionable]


def monthly_fee_accrual(dataset: Dataset) -> dict[str, tuple[int, int, int]]:
    """(taxable, tax, rows) of Razorpay fee per settlement month.

    Razorpay invoices fees MONTHLY, so one GSTR-2B line ties back to N
    settlements. Rows charged a fee with NO GST are excluded from taxable
    value -- there is no input tax on them to claim -- and counted separately.
    """
    accrual: dict[str, list[int]] = {}
    for row in dataset.rows:
        if row["type"] != "payment" or not row["settled_at"] or not row["fee"]:
            continue
        month = to_date(row["settled_at"]).strftime("%Y-%m")
        bucket = accrual.setdefault(month, [0, 0, 0])
        if row["tax"]:
            bucket[0] += row["fee"] - row["tax"]
            bucket[1] += row["tax"]
            bucket[2] += 1
    return {month: tuple(values) for month, values in sorted(accrual.items())}


def identify_supplier(dataset: Dataset, accrual) -> str | None:
    """Find the payment gateway's GSTIN in 2B by tying it to the fee ledger.

    Nothing in the data labels which supplier is the gateway. It is identified
    the same way an accountant would: the supplier whose invoice taxable values
    reconcile to the fee actually deducted, month by month.
    """
    targets = {month: values[0] for month, values in accrual.items()}
    best, best_hits = None, 0
    by_gstin: dict[str, list[Gstr2bLine]] = defaultdict(list)
    for line in dataset.gstr2b:
        by_gstin[line.gstin].append(line)
    for gstin, lines in sorted(by_gstin.items()):
        hits = sum(
            1 for line in lines
            for month, taxable in targets.items()
            if abs(line.taxable_value - taxable)
            <= max(1, accrual[month][2]) * TOLERANCE_PAISE_PER_ROW
        )
        if hits > best_hits:
            best, best_hits = gstin, hits
    return best


def analyse_tax(dataset: Dataset) -> TaxFindings:
    findings = TaxFindings()
    accrual = monthly_fee_accrual(dataset)
    findings.monthly_accrual = {m: (v[0], v[1]) for m, v in accrual.items()}

    for row in dataset.rows:
        if row["type"] == "payment" and row["fee"] and not row["tax"]:
            findings.fee_charged_without_gst_paise += row["fee"]
            findings.fee_without_gst_rows.append(row["entity_id"])
    findings.fee_without_gst_rows.sort()

    supplier = identify_supplier(dataset, accrual)
    findings.supplier_gstin = supplier
    if supplier is None:
        return findings

    supplier_lines = sorted(
        (line for line in dataset.gstr2b if line.gstin == supplier),
        key=lambda line: line.invoice_date)
    invoiced_periods = {line.gstr1_filing_period: line for line in supplier_lines}

    for month, (taxable, tax, rows) in accrual.items():
        line = invoiced_periods.get(month)
        if line is None:
            continue
        tolerance = max(1, rows) * TOLERANCE_PAISE_PER_ROW
        residual = line.tax_total - tax
        if residual:
            findings.rounding_residuals.append({
                "period": month,
                "invoice_no": line.invoice_no,
                "accrued_tax_paise": tax,
                "invoiced_tax_paise": line.tax_total,
                "residual_paise": residual,
                "within_tolerance": abs(residual) <= tolerance,
                "tolerance_paise": tolerance,
            })
    return findings


def _tax_exceptions(dataset: Dataset, findings: TaxFindings) -> list[Exception_]:
    if findings.supplier_gstin is None:
        return []
    out: list[Exception_] = []
    supplier_lines = [line for line in dataset.gstr2b
                      if line.gstin == findings.supplier_gstin]
    by_period = {line.gstr1_filing_period: line for line in supplier_lines}

    for month, (taxable, tax) in findings.monthly_accrual.items():
        if month in by_period:
            continue
        out.append(Exception_(
            type="gstr2b_absent",
            entity_id=f"period:{month}",
            evidence={"period": month, "invoice_no": "(none in 2B)",
                      "itc": inr(tax), "itc_paise": tax,
                      "accrued_taxable": rupees(taxable),
                      "statute": "Sec 16(2)(aa) CGST"},
            proposed_je=f"Dr ITC ineligible {inr(tax)} / Cr Input GST {inr(tax)}",
            confidence=CONFIDENCE_FROM_ABSENCE, owner=OWNERS["gstr2b_absent"]))
        findings.itc_at_risk_paise += tax
        findings.itc_lines.append({"period": month, "reason": "gstr2b_absent",
                                   "itc_paise": tax})

    for line in sorted(supplier_lines, key=lambda x: x.invoice_no):
        if not line.has_irn:
            out.append(Exception_(
                type="gstr2b_no_irn",
                entity_id=line.invoice_no,
                evidence={"invoice_no": line.invoice_no,
                          "period": line.gstr1_filing_period,
                          "itc": inr(line.tax_total), "itc_paise": line.tax_total,
                          "statute": "Rule 48(5) CGST"},
                proposed_je=(f"Dr ITC ineligible {inr(line.tax_total)} / "
                             f"Cr Input GST {inr(line.tax_total)}"),
                confidence=CONFIDENCE_EXPLICIT, owner=OWNERS["gstr2b_no_irn"]))
            findings.itc_at_risk_paise += line.tax_total
            findings.itc_lines.append({"period": line.gstr1_filing_period,
                                       "reason": "gstr2b_no_irn",
                                       "itc_paise": line.tax_total})
        if line.supplier_gstr3b_filed.upper() == "N":
            # 2B still reports itc_availability Yes. The exposure is invisible
            # in the return and has to be COMPUTED, which is the whole point.
            out.append(Exception_(
                type="gstr2b_37a_exposure",
                entity_id=line.invoice_no,
                evidence={"invoice_no": line.invoice_no,
                          "period": line.gstr1_filing_period,
                          "itc": inr(line.tax_total), "itc_paise": line.tax_total,
                          "itc_availability_in_2b": line.itc_availability,
                          "statute": "Rule 37A CGST"},
                proposed_je=(f"Dr ITC reversal {inr(line.tax_total)} / "
                             f"Cr Input GST {inr(line.tax_total)} (plus interest)"),
                confidence=CONFIDENCE_EXPLICIT, owner=OWNERS["gstr2b_37a_exposure"]))
            findings.itc_at_risk_paise += line.tax_total
            findings.itc_lines.append({"period": line.gstr1_filing_period,
                                       "reason": "gstr2b_37a_exposure",
                                       "itc_paise": line.tax_total})
    return out


def run(
    dataset: Dataset,
    stage1,
    stage3: Stage3Result,
    explainer: Explainer | None = None,
) -> Stage4Result:
    explainer = explainer or get_explainer("deterministic")
    result = Stage4Result()
    horizon = max(line.value_date for line in dataset.bank)

    netted_payments = {group.payment_id for group in stage3.zero_net_groups}
    netted_refunds = {rid for group in stage3.zero_net_groups
                      for rid in group.refund_ids}
    netted_amount = {group.payment_id: group.amount for group in stage3.zero_net_groups}
    resolved = set(stage3.assigned) | set(stage3.contested)

    for row in sorted(dataset.rows, key=lambda r: r["entity_id"]):
        row_id = row["entity_id"]

        # A lost-dispute adjustment DOES belong to a batch -- it is a debit row
        # and the balance identity needs it. What it can never have is a
        # COUNTERPARTY: no payment_id, no order_id, no method. So it is
        # reported whether or not Stage 3 placed it, because "which batch"
        # and "which payment" are different questions and only the second is
        # unanswerable.
        if is_unjoinable_adjustment(row) and row["dispute_id"]:
            result.exceptions.append(_make(
                "lost_dispute_adjustment", row_id,
                {"amount": rupees(row["amount"]), "dispute_id": row["dispute_id"],
                 "description": row["description"],
                 "settled_in_batch": row_id in stage3.assigned,
                 "counterparty": "none by construction"},
                f"Dr Chargeback losses {inr(row['amount'])} / "
                f"Cr Settlement receivable {inr(row['amount'])}",
                CONFIDENCE_EXPLICIT, explainer))
            continue

        if row_id in stage3.assigned:
            continue

        if row_id in stage3.contested:
            reconstruction = stage3.by_bank_index(stage3.contested[row_id])
            count = len(reconstruction.resolution.candidates) if reconstruction else 0
            result.exceptions.append(_make(
                "ambiguous_batch_membership", row_id,
                {"candidate_count": count,
                 "bank_index": stage3.contested[row_id],
                 "amount": rupees(row["amount"])},
                None, CONFIDENCE_DERIVED, explainer))
            continue

        if is_failed(row):
            result.exceptions.append(_make(
                "failed_payment_never_settles", row_id,
                {"amount": rupees(row["amount"]), "fee": "null", "tax": "null",
                 "error": row.get("error_reason") or "gateway_declined"},
                None, CONFIDENCE_EXPLICIT, explainer))
            continue

        if row["on_hold"]:
            result.exceptions.append(_make(
                "dispute_hold_pending", row_id,
                {"dispute_id": row["dispute_id"], "amount": rupees(row["amount"])},
                None, CONFIDENCE_EXPLICIT, explainer))
            continue

        if row_id in netted_payments or row_id in netted_refunds:
            anchor = row_id if row_id in netted_payments else row["payment_id"]
            result.exceptions.append(_make(
                "netted_out_by_full_refund", row_id,
                {"amount": rupees(netted_amount.get(anchor, row["amount"])),
                 "payment_id": anchor},
                None, CONFIDENCE_DERIVED, explainer))
            continue

        if row["type"] == "payment":
            eligible = eligible_from(row)
            kind = ("subset_sum_rolled_forward" if eligible <= horizon
                    else "not_yet_eligible")
            result.exceptions.append(_make(
                kind, row_id,
                {"amount": rupees(row["amount"]),
                 "captured_on": to_date(row["created_at"]).isoformat(),
                 "eligible_on": eligible.isoformat(),
                 "statement_ends": horizon.isoformat()},
                None, CONFIDENCE_DERIVED, explainer))
            continue

        result.exceptions.append(_make(
            "deferred_debit_pending", row_id,
            {"amount": rupees(row["amount"]),
             "raised_on": to_date(row["created_at"]).isoformat(),
             "type": row["type"]},
            None, CONFIDENCE_DERIVED, explainer))

    erp_by_order = {order.order_id: order for order in dataset.erp}
    rows_by_id = {row["entity_id"]: row for row in dataset.rows}
    for row_id in stage1.rows_without_erp:
        row = rows_by_id[row_id]
        result.exceptions.append(_make(
            "erp_gap_no_order", row_id,
            {"order_id": row["order_id"], "amount": rupees(row["amount"]),
             "settled": bool(row["settlement_id"])},
            f"Dr Bank {inr(row['credit'])} / Cr Unrecorded revenue "
            f"{inr(row['credit'])}",
            CONFIDENCE_FROM_ABSENCE, explainer))

    erp_by_invoice = {order.invoice_no: order for order in dataset.erp}
    for invoice_no in stage1.erp_unjoined:
        order = erp_by_invoice[invoice_no]
        result.exceptions.append(_make(
            "erp_gap_no_payment", invoice_no,
            {"invoice_no": invoice_no, "amount": rupees(order.amount),
             "order_id": order.order_id,
             "invoice_date": order.invoice_date.isoformat()},
            f"Dr Trade receivable {inr(order.amount)} / Cr Revenue "
            f"{inr(order.amount)} (or reverse if raised in error)",
            CONFIDENCE_FROM_ABSENCE, explainer))

    for reconstruction in stage3.reconstructions:
        from .model import Unresolved
        if isinstance(reconstruction.resolution, Unresolved):
            result.exceptions.append(_make(
                "genuinely_unresolved", f"bank[{reconstruction.bank_index}]",
                {"bank_amount": rupees(reconstruction.bank_amount),
                 "pool_size": reconstruction.resolution.pool_size,
                 "reason": reconstruction.resolution.reason},
                None, CONFIDENCE_DERIVED, explainer))

    result.tax = analyse_tax(dataset)
    tax_exceptions = _tax_exceptions(dataset, result.tax)
    for item in tax_exceptions:
        result.exceptions.append(_narrate(item, explainer))

    result.exceptions.sort(key=lambda item: (item.type, item.entity_id))
    return result


def _make(kind, entity_id, evidence, proposed_je, confidence, explainer) -> Exception_:
    item = Exception_(type=kind, entity_id=entity_id, evidence=evidence,
                      proposed_je=proposed_je, confidence=confidence,
                      owner=OWNERS[kind])
    return _narrate(item, explainer)


def _narrate(item: Exception_, explainer: Explainer) -> Exception_:
    from dataclasses import replace
    return replace(item, narrative=explainer.explain(ExplanationRequest(
        exception_type=item.type, entity_id=item.entity_id,
        evidence=item.evidence, proposed_je=item.proposed_je, owner=item.owner)))
