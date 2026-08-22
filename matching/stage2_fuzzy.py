"""Stage 2 -- blocking and fuzzy candidates for what Stage 1 could not join.

Two jobs, and one thing this stage deliberately REFUSES to do.

1. Recover bank lines whose join key is unusable. Two distinct failures look
   the same from Stage 1 and are not the same problem:
     - the bank statement's `utr` column is blank (the key is gone from the
       BANK side);
     - the batch consists only of adjustment rows, which carry a null
       `settlement_utr`, so there is no key on the LEDGER side either.
   Both fall back to (amount, value_date), which the dataset guarantees is
   unambiguous -- but only for a matcher that has the fallback.

2. Corroborate with narration similarity where narration survives.

3. It does NOT bridge the ERP gaps. Some settled payments have no ERP order
   and some ERP orders have no payment. Those are REAL gaps. Amount-and-date
   similarity will happily pair an orphan invoice with an unrecorded payment,
   and that pair is a false positive: it asserts a relationship that does not
   exist and closes a genuine control failure. Candidates are generated, then
   rejected for want of corroboration, and the rejections are REPORTED -- an
   engine that silently declines is indistinguishable from one that never
   looked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from rapidfuzz import fuzz

from .loaders import Dataset, to_date
from .stage1_exact import Stage1Result

#: Amount tolerance is per-row, not per-batch: the only legitimate source of
#: drift is +/-1 paise of ceiling-rounding per fee-bearing row, so the budget
#: must scale with how many rows the amount aggregates. A flat +/-Rs 1 window
#: across a 20-payment batch spans a range wide enough to admit a wrong subset,
#: which is exactly the false positive this cascade is built to avoid.
TOLERANCE_PAISE_PER_ROW = 1
#: Bank-line date and settlement date are the same calendar day in this ledger;
#: one day either side absorbs a value-date convention difference without
#: opening the window far enough to admit an adjacent weekly batch.
DATE_WINDOW_DAYS = 1
#: Below this, a narration is treated as carrying no usable signal at all.
NARRATION_FLOOR = 60.0
#: Blocking and gating are different jobs and get different windows. BLOCKING
#: should have generous recall -- a pair it never proposes can never be
#: examined, and "we found nothing" is not the same claim as "we looked and
#: refused". The GATE is where precision lives. These wide values are used only
#: to surface ERP candidates for refusal; nothing is ever matched on them.
ERP_BLOCK_AMOUNT_BASIS_POINTS = 200          # +/-2% of the payment amount
ERP_BLOCK_DATE_WINDOW_DAYS = 3


def amount_tolerance(row_count: int) -> int:
    """Paise of slack permitted on an amount aggregating `row_count` rows."""
    return max(0, row_count) * TOLERANCE_PAISE_PER_ROW


@dataclass(frozen=True, slots=True)
class RejectedCandidate:
    """A pair that blocking proposed and the gate refused."""

    left: str
    right: str
    reason: str
    amount_delta: int
    day_delta: int
    narration_score: float | None = None


@dataclass
class Stage2Result:
    #: settlement_id -> bank line index, recovered without a UTR
    batch_to_bank: dict[str, int] = field(default_factory=dict)
    bank_to_batch: dict[int, str] = field(default_factory=dict)
    recovery_notes: dict[int, str] = field(default_factory=dict)
    still_unjoined_bank: list[int] = field(default_factory=list)
    rejected: list[RejectedCandidate] = field(default_factory=list)
    narration_scores: dict[int, float] = field(default_factory=dict)


def narration_similarity(narration: str, expected: str) -> float:
    return float(fuzz.token_set_ratio(narration, expected))


def _expected_narration(utr: str | None) -> str:
    base = "NEFT-CR-RATN0000088-RAZORPAY SOFTWARE PVT LTD-ACME RETAIL PRIVATE LIMITED"
    return f"{base}-{utr}" if utr else base


def run(dataset: Dataset, stage1: Stage1Result) -> Stage2Result:
    result = Stage2Result()

    open_bank = [dataset.bank[i] for i in stage1.bank_unjoined]
    open_batches = {sid: batch for sid, batch in stage1.batches.items()
                    if sid not in stage1.batch_to_bank}

    for line in open_bank:
        tolerance_by_batch = {
            sid: amount_tolerance(len(batch.row_ids))
            for sid, batch in open_batches.items()
        }
        hits = []
        for sid, batch in open_batches.items():
            delta = batch.net - line.amount
            days = abs((batch.settled_on - line.value_date).days)
            if abs(delta) <= tolerance_by_batch[sid] and days <= DATE_WINDOW_DAYS:
                hits.append((sid, delta, days))

        if not hits:
            result.still_unjoined_bank.append(line.index)
            continue

        if len(hits) > 1:
            # Refuse rather than guess. Two batches indistinguishable on
            # (amount, date) means the fallback has no evidence to choose with.
            for sid, delta, days in hits:
                result.rejected.append(RejectedCandidate(
                    left=f"bank[{line.index}]", right=sid,
                    reason="ambiguous_amount_date_fallback",
                    amount_delta=delta, day_delta=days))
            result.still_unjoined_bank.append(line.index)
            continue

        sid, delta, days = hits[0]
        score = narration_similarity(
            line.narration, _expected_narration(open_batches[sid].utr_hint))
        result.narration_scores[line.index] = score
        result.batch_to_bank[sid] = line.index
        result.bank_to_batch[line.index] = sid
        missing = ("bank utr column blank" if not line.has_join_key
                   else "ledger settlement_utr null (adjustment-only batch)")
        result.recovery_notes[line.index] = (
            f"recovered on (amount, value_date); {missing}; "
            f"amount delta {delta} paise, {days} day(s); "
            f"narration similarity {score:.1f}")
        del open_batches[sid]

    result.rejected.extend(_erp_gap_candidates(dataset, stage1))
    return result


def _erp_gap_candidates(dataset: Dataset, stage1: Stage1Result) -> list[RejectedCandidate]:
    """Propose ERP pairs on amount+date, then refuse every one of them.

    The corroboration gate requires a shared identifier -- `order_id`, or a
    receipt appearing in the invoice number. Amount and date alone are not
    evidence of identity: this ledger contains deliberate same-amount same-day
    decoy pairs precisely so that a matcher relying on them is caught.

    Reporting the refusals is the point. It shows the gap was examined and
    found real, rather than never looked at.
    """
    rejected: list[RejectedCandidate] = []
    orphan_invoices = {order.invoice_no: order for order in dataset.erp
                       if order.invoice_no in set(stage1.erp_unjoined)}
    unrecorded = [row for row in dataset.rows
                  if row["entity_id"] in set(stage1.rows_without_erp)]

    for row in unrecorded:
        row_date = to_date(row["created_at"])
        for invoice_no, order in sorted(orphan_invoices.items()):
            delta = order.amount - row["amount"]
            days = abs((order.invoice_date - row_date).days)
            window = row["amount"] * ERP_BLOCK_AMOUNT_BASIS_POINTS // 10000
            if abs(delta) > window or days > ERP_BLOCK_DATE_WINDOW_DAYS:
                continue
            rejected.append(RejectedCandidate(
                left=row["entity_id"], right=invoice_no,
                reason="no_shared_identifier_amount_and_date_are_not_identity",
                amount_delta=delta, day_delta=days,
                narration_score=float(fuzz.ratio(row["order_id"], order.order_id)),
            ))
    return rejected
