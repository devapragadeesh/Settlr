"""The LLM leg -- explainer and narrator, never matcher.

## The governing rule

Matching is arithmetic. A model asked to decide whether a row belongs to a
batch will sometimes say yes when the sum does not close, cannot show a proof,
and will not give the same answer twice. So no model output is ever consulted
by Stages 1-3, and Stage 4's `type` and `owner` -- the fields that determine
what HAPPENS to a row -- are assigned by deterministic rules.

What the model may do: turn a classified exception into a sentence a finance
controller can act on. That is genuinely useful and carries no risk, because
the classification is already fixed before the adapter is called.

## Determinism

The default adapter is the deterministic one. The pipeline, the eval report and
every test run with no model in the loop and produce byte-identical output. A
live model is opt-in via `--llm`, and its output is confined to the `narrative`
field, which nothing downstream reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExplanationRequest:
    exception_type: str
    entity_id: str
    evidence: dict
    proposed_je: str | None
    owner: str


class Explainer(Protocol):
    name: str

    def explain(self, request: ExplanationRequest) -> str:
        ...


TEMPLATES = {
    "subset_sum_rolled_forward":
        "Eligible on {eligible_on} but not drawn into any settlement in the "
        "window; live balance was insufficient to include it. Expect it in a "
        "later batch. No action.",
    "not_yet_eligible":
        "Captured {captured_on}; reaches T+2 eligibility on {eligible_on}, "
        "after the statement period. No action.",
    "dispute_hold_pending":
        "Funds locked against dispute {dispute_id}; excluded from live balance "
        "until the dispute resolves. Blocked, not missing.",
    "lost_dispute_adjustment":
        "Chargeback debit carrying no payment_id, order_id or method. "
        "Unjoinable by construction -- there is no counterparty row to find.",
    "netted_out_by_full_refund":
        "Refunded in full for {amount} before it could settle; payment and "
        "refund cancel and neither is ever paid out. Correct as-is.",
    "failed_payment_never_settles":
        "Payment failed at the gateway; fee and tax are null, not zero. Never "
        "enters a batch.",
    "deferred_debit_pending":
        "Debit of {amount} could not be applied without driving the payout "
        "negative; deferred to a later batch.",
    "erp_gap_no_order":
        "Money received and settled, but no ERP order exists for {order_id}. "
        "Revenue recognised by the bank and not by the books.",
    "erp_gap_no_payment":
        "ERP invoice {invoice_no} for {amount} has no corresponding payment. "
        "Either unbilled or recorded in error.",
    "gstr2b_absent":
        "Supplier invoice {invoice_no} for period {period} never appeared in "
        "GSTR-2B. ITC of {itc} is not available under Sec 16(2)(aa) CGST.",
    "gstr2b_no_irn":
        "Supplier invoice {invoice_no} carries no IRN. Under Rule 48(5) CGST "
        "it is not a tax invoice, so ITC of {itc} fails for want of a valid "
        "document.",
    "gstr2b_37a_exposure":
        "Supplier has not filed GSTR-3B for {period}. GSTR-2B still reports "
        "itc_availability Yes, so this exposure is not visible in 2B and must "
        "be computed: {itc} is reversible under Rule 37A with interest.",
    "ambiguous_batch_membership":
        "Bank credit admits {candidate_count} equally valid decompositions. "
        "Membership cannot be determined from the statement alone.",
    "genuinely_unresolved":
        "No subset of the eligible pool nets to this bank credit. Requires "
        "manual investigation.",
}


class DeterministicExplainer:
    """Template narration. The default, and what every test runs against."""

    name = "deterministic"

    def explain(self, request: ExplanationRequest) -> str:
        template = TEMPLATES.get(request.exception_type)
        if template is None:
            return f"Unclassified exception on {request.entity_id}."
        try:
            return template.format(**request.evidence)
        except KeyError as missing:
            return (f"{request.exception_type} on {request.entity_id} "
                    f"(evidence incomplete: {missing})")


class ClaudeExplainer:
    """Opt-in live narration.

    Receives the classification and the evidence and is asked to phrase them.
    It is never given the option to change `exception_type` or `owner`, and its
    output is written only to `narrative`, which no downstream stage reads. If
    the call fails the deterministic explainer answers instead -- an
    unavailable model must never change what the pipeline decides.
    """

    name = "claude"

    def __init__(self, model: str = "claude-sonnet-5") -> None:
        self.model = model
        self._fallback = DeterministicExplainer()

    def explain(self, request: ExplanationRequest) -> str:
        try:
            import anthropic
        except ImportError:
            return self._fallback.explain(request)
        try:
            client = anthropic.Anthropic()
            message = client.messages.create(
                model=self.model,
                max_tokens=160,
                system=(
                    "You explain reconciliation exceptions to a finance "
                    "controller. You are given a CLASSIFICATION that has "
                    "already been decided by arithmetic. Do not question it, "
                    "do not propose a different match, do not perform "
                    "calculations. Write at most two sentences saying what "
                    "happened and what the owner should do."),
                messages=[{"role": "user", "content": (
                    f"type: {request.exception_type}\n"
                    f"entity: {request.entity_id}\n"
                    f"owner: {request.owner}\n"
                    f"evidence: {request.evidence}\n"
                    f"proposed journal entry: {request.proposed_je}")}],
            )
            return message.content[0].text.strip()
        except Exception:
            return self._fallback.explain(request)


def get_explainer(name: str = "deterministic") -> Explainer:
    return ClaudeExplainer() if name == "claude" else DeterministicExplainer()
