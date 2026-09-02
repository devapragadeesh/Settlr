"""Disposition of every row no bank line took: `ProvenUnmatched` or `OpenBreak`.

Contract sec 4.7. This module exists because the outcome it replaces asserted
one thing and was used for two:

* *the ledger entails no bank credit exists for this row* -- a positive claim;
* *I did not place this row* -- an absence of evidence, reported as if it were
  the first.

Measured over 4,994 claims, the second was 14.6% right and the first 97.6%,
and every report in the repository called the combination "0 wrong answers"
because that phrase was scoped to `Verified` alone
(`investigation/DERIVED_BRANCH_AUDIT.md`).

**The admission test is ENTAILMENT, not accuracy.** That distinction is
load-bearing and counter-intuitive: correcting the old derivations to
transcribe `engine/simulator.py` exactly made the REASONS more accurate
(36 wrong -> 10) and the soundness gate FIVE TIMES WORSE (8 rows-that-settled
-> 64), because a corrected `dispute_held` promotes rows out of a residual
that asserts nothing into a branch that asserts something false.

Nothing here reads ground truth.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from resolver_contract.types import (
    BreakReason, Evidence, EvidenceKind, OpenBreak, ProvenUnmatched,
    ProvenUnmatchedReason, SourceSystem, Warrant,
)

from resolver.eligibility import IST, eligible_at

PSP = frozenset({SourceSystem.PSP_LEDGER})


# --------------------------------------------------------------------------
# the two entailments, transcribed from the frozen simulator
# --------------------------------------------------------------------------


def netted_out_payments(rows: list[dict]) -> set[str]:
    """Payment ids whose refunds annihilate them before they became eligible.

    A TRANSCRIPTION of `engine/simulator.py` (the normative implementation of
    `SETTLEMENT_SPEC.md` sec 3), not a paraphrase of it:

        sum(r.amount for r in rs) == p.amount
        and all(r.created_at <= eligible_at[p.id] for r in rs)

    The first resolver wrote this as `sum(refund.debit) >= payment.credit` with
    no timing test, and each of those three divergences alone produced false
    claims:

    * `>=` instead of `==` admits an OVER-refunded payment, which settles;
    * `payment.credit` is `amount - fee`, so a refund short of the gross by
      less than the fee reads as full. Measured: a payment of 2,014,900 paise
      with refunds of 2,014,800 -- one rupee short -- passed, because it was
      being compared against a number a 4,752-paise fee had already reduced;
    * with no timing test, a refund raised weeks AFTER settlement counts as
      though it had prevented the settlement.

    Returns payment ids only; the caller maps refunds through `payment_id`.
    """
    refunds_of: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["type"] == "refund" and row.get("payment_id"):
            refunds_of[row["payment_id"]].append(row)

    netted: set[str] = set()
    for row in rows:
        if row["type"] != "payment":
            continue
        rs = refunds_of.get(row["entity_id"])
        if not rs:
            continue
        deadline = eligible_at(row["created_at"])
        if (sum(r["debit"] for r in rs) == row["amount"]
                and all(r["created_at"] <= deadline for r in rs)):
            netted.add(row["entity_id"])
    return netted


def _proven_reason(row: dict, netted: set[str]) -> ProvenUnmatchedReason | None:
    """The row's entailment, or None if the ledger entails nothing about it."""
    if row["type"] == "payment":
        if row["credit"] == 0:
            return ProvenUnmatchedReason.NOT_CAPTURED
        if row["entity_id"] in netted:
            return ProvenUnmatchedReason.NETTED_OUT
        return None
    if row["type"] == "refund":
        parent = row.get("payment_id")
        if parent and parent in netted:
            return ProvenUnmatchedReason.NETTED_OUT
    return None


# --------------------------------------------------------------------------
# aging
# --------------------------------------------------------------------------


def first_reconcilable(row: dict) -> int:
    """When the item first became something that COULD have settled.

    A payment cannot settle before `eligible_at`; a debit applies immediately
    (`SETTLEMENT_SPEC.md` sec 3). Aging a payment from `created_at` would
    charge it for the T+2 window the product promises.
    """
    if row["type"] == "payment":
        return eligible_at(row["created_at"])
    return row["created_at"]


def _age(row: dict, horizon: date) -> tuple[int, str]:
    seen = datetime.fromtimestamp(first_reconcilable(row), IST).date()
    return max(0, (horizon - seen).days), seen.isoformat()


def _month(row: dict) -> str:
    """The reporting month this item first became reconcilable in.

    NOT `settled_at`. Every row reaching this module is a row nothing placed,
    and an unplaced row has no settlement month the resolver is entitled to
    read as its own -- `settled_at` is a PSP claim about an event the resolver
    could not confirm, and for an unsettled row it is null outright. So the
    attribution is the same clock `_age` already uses: when the item first
    became something that COULD have settled. Where the two differ the flag is
    conservative in the direction of the earlier month, and it is a flag on an
    open item either way, never an assignment.
    """
    return datetime.fromtimestamp(first_reconcilable(row), IST).strftime("%Y-%m")


# --------------------------------------------------------------------------
# input tax credit exposure -- descriptive, never dispositive
# --------------------------------------------------------------------------

#: Per fee-bearing row, how far an invoiced taxable value may sit from the
#: accrued one and still be the same invoice. One paise per row: the gap is
#: rounding, and rounding is bounded by the number of roundings.
_TOLERANCE_PAISE_PER_ROW = 1

#: The three grounds, named once. Statutes cited for the operator, not used.
GROUND_ABSENT = "gstr2b_absent"              # sec 16(2)(aa) CGST
GROUND_NO_IRN = "gstr2b_no_irn"              # Rule 48(5) CGST
GROUND_37A = "gstr2b_37a_exposure"           # Rule 37A CGST


def _accrues_input_tax(row: dict) -> bool:
    """Did THIS row generate a gateway fee carrying input tax the merchant
    could claim?

    Named once and used in the two places that must not disagree: the monthly
    accrual below, which decides which months are at risk, and the per-row
    annotation in `dispositions()`, which decides which rows may be told about
    it. Sec 61 is the entry for what happens when they do disagree -- the flag
    fired on four rows that had never settled, purely because they shared a
    calendar month with the settled population the risk actually belongs to.

    Every clause is load-bearing and none is a proxy for another:

    * `type == "payment"` -- a refund or an adjustment is not a supply the
      gateway invoices for;
    * `settled_at` -- the PSP's own claim that the settlement happened. A fee
      is charged out of a payout; no payout, no fee, no invoice, no input tax.
      A `fee` field on an unsettled row is a PROSPECTIVE charge and every one
      of the four false positives carried one, so gating on `fee` alone would
      not have caught them;
    * `fee` and `tax` -- a fee with no GST on it carries no credit to lose.

    Note what this does NOT claim. `settled_at` is the PSP asserting a
    settlement the resolver could not corroborate (which is precisely why the
    row reached `dispositions()` at all). That is enough to make an ITC
    exposure PLAUSIBLE, which is all a flag on an open item ever claims; it
    would not be enough to place the row in a bank credit, and nothing here
    does.
    """
    return bool(row["type"] == "payment"
                and row.get("settled_at")
                and row.get("fee")
                and row.get("tax"))


def _fee_accrual(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """`settlement month -> (taxable fee, tax)` the gateway accrued.

    Rows charged a fee with no GST contribute NEITHER leg: there is no input
    tax on them to claim, so including their fee in the taxable value would
    manufacture a mismatch against an invoice that correctly omits them. The
    month here IS `settled_at`, because this side of the calculation is about
    what the gateway invoiced for, not about what the resolver could place.

    A fee-bearing row with no GST on it still OPENS its month's bucket while
    contributing nothing to either leg. That asymmetry is deliberate and is
    load-bearing for `gstr2b_absent`: the month saw settlement activity and so
    is a month a 2B line could be missing from, even though this particular row
    puts no value in it.
    """
    accrual: dict[str, list[int]] = {}
    for row in rows:
        if row["type"] != "payment" or not row.get("settled_at"):
            continue
        if not row.get("fee"):
            continue
        month = datetime.fromtimestamp(row["settled_at"], IST).strftime("%Y-%m")
        bucket = accrual.setdefault(month, [0, 0, 0])
        if _accrues_input_tax(row):
            bucket[0] += row["fee"] - row["tax"]
            bucket[1] += row["tax"]
            bucket[2] += 1
    return {month: tuple(values) for month, values in sorted(accrual.items())}


def gateway_gstin(dataset) -> str | None:
    """Which supplier in 2B is the payment gateway.

    Nothing in the data says. It is identified the way an accountant would: the
    supplier whose invoiced taxable values reconcile, month by month, to the
    fee the ledger actually shows deducted. A supplier that matches nothing
    scores zero and `None` is returned rather than a guess -- with no gateway
    identified there is no ITC finding to make, which is the correct answer and
    not a degraded one.

    This is an INDEPENDENT reimplementation of the logic shape in
    `matching/stage4_exceptions.py`, which this package may not import. Two
    implementations of one statutory rule can drift, so
    `resolver/tests/test_gst_risk.py` asserts the two agree on every GST
    dataset in the corpus. That test is the mitigation, not a nicety.
    """
    lines = getattr(dataset, "gstr2b", []) or []
    if not lines:
        return None
    accrual = _fee_accrual(dataset.rows)
    by_gstin: dict[str, list] = defaultdict(list)
    for line in lines:
        by_gstin[line.gstin].append(line)

    best, best_hits = None, 0
    for gstin, supplier_lines in sorted(by_gstin.items()):
        hits = sum(
            1
            for line in supplier_lines
            for month, values in accrual.items()
            if abs(line.taxable_value - values[0])
            <= max(1, values[2]) * _TOLERANCE_PAISE_PER_ROW)
        # Strictly greater: a tie keeps the first supplier in GSTIN order, so
        # the answer does not depend on dict insertion order.
        if hits > best_hits:
            best, best_hits = gstin, hits
    return best


def _itc_risk_months(dataset) -> dict[str, tuple[str, ...]]:
    """`"YYYY-MM" -> the grounds on which that month's input tax credit is at
    risk`. Months with no ground are absent from the mapping.

    ITC risk in this data is MONTH-level and cannot honestly be made
    row-level: the gateway invoices its fees monthly, so one 2B line stands
    behind every settlement in a period, and no recon row carries an
    `invoice_no` to tie it to one. A per-row citation would be a precision this
    evidence does not have.

    Three grounds, each independently determinable:

    * `gstr2b_absent` -- the ledger accrued gateway fees in a month and no 2B
      line from the gateway carries that filing period. There is no document to
      claim the credit against (sec 16(2)(aa) CGST).
    * `gstr2b_no_irn` -- a gateway line with no invoice reference number. An
      e-invoice without an IRN is not a valid tax invoice (Rule 48(5) CGST).
    * `gstr2b_37a_exposure` -- the supplier has not filed GSTR-3B. 2B still
      reports the credit as available; the exposure is invisible in the return
      and has to be computed, which is the entire point (Rule 37A CGST).

    The last two are attributed to the line's own `gstr1_filing_period`, the
    period the document belongs to, not to its invoice date.

    Nothing here decides anything. The caller may only ANNOTATE rows it has
    already given up on -- and a month being at risk is a NECESSARY condition
    for annotating a row in it, never a sufficient one. The risk belongs to the
    population that accrued the fees; `dispositions()` must additionally check
    that the individual row is part of that population (`_accrues_input_tax`),
    or it reports every open row in a bad month as exposed. Sec 60 measured
    that error and sec 61 is the fix.
    """
    lines = getattr(dataset, "gstr2b", []) or []
    supplier = gateway_gstin(dataset)
    if supplier is None:
        return {}

    grounds: dict[str, set[str]] = defaultdict(set)
    supplier_lines = [line for line in lines if line.gstin == supplier]
    periods = {line.gstr1_filing_period for line in supplier_lines}

    for month in _fee_accrual(dataset.rows):
        if month not in periods:
            grounds[month].add(GROUND_ABSENT)

    for line in supplier_lines:
        # Not elif: one invoice can carry both, and reporting either alone
        # would understate the exposure.
        if not line.has_irn:
            grounds[line.gstr1_filing_period].add(GROUND_NO_IRN)
        if line.supplier_gstr3b_filed.upper() == "N":
            grounds[line.gstr1_filing_period].add(GROUND_37A)

    return {month: tuple(sorted(found))
            for month, found in sorted(grounds.items()) if found}


# --------------------------------------------------------------------------
# classification of everything the entailments do not cover
# --------------------------------------------------------------------------


def _break_reason(row: dict, horizon: date, blocked_by: int | None,
                  disputes: dict[str, dict]
                  ) -> tuple[BreakReason, int | None, bool]:
    """`(reason, caused_by, provable_within_window)`. Asserts nothing.

    Order matters, and it is not the frozen simulator's order. The simulator
    answers *"why did this row not settle"* knowing that it did not. This
    answers *"why is this item open"*, and an item blocked by an unresolved
    finding about a BANK LINE is that, whatever else is also true of it --
    routing it to disputes ops because it happens to carry a hold would send
    it to someone who cannot close it.
    """
    if blocked_by is not None:
        return BreakReason.UPSTREAM_UNRESOLVED, blocked_by, False

    # Not eligible by the horizon => it cannot be in any observed credit.
    # Entailed, and by a PROVABLE margin rather than by luck: this horizon is
    # the last bank `value_date`, which is always LATER than the last batch
    # time by the posting lag, so the test is strictly stronger than the one
    # the answer key applies and can miss but never false-positive.
    #
    # It is still an OpenBreak. `ProvenUnmatched` means no bank credit exists;
    # a not-yet-eligible row's bank credit exists next Tuesday. Gating a
    # temporary state as a permanent proof is how the distinction rots
    # (contract sec 4.7.4).
    if row["type"] == "payment":
        if first_reconcilable(row) > int(datetime.combine(
                horizon, datetime.min.time(), tzinfo=IST).timestamp()) + 86_400:
            return BreakReason.TIMING_DIFFERENCE, None, True

        dispute = disputes.get(row.get("dispute_id") or "")
        if dispute is not None or row.get("on_hold"):
            # NOT ProvenUnmatched, and not because the implementation is weak.
            # A hold does not entail non-settlement: `retrieval` and `fraud`
            # withhold, but `chargeback` claws back AFTER settlement. All 31
            # lost chargebacks in the corpus settled and were then reversed.
            return BreakReason.UNEXPECTED_CHANGE, None, False

    return BreakReason.UNEXPLAINED, None, False


def dispositions(dataset, consumed: set[str], blocked: dict[str, int],
                 ) -> list:
    """Every unconsumed row, split into what is entailed and what is open."""
    horizon = max(line.value_date for line in dataset.bank)
    netted = netted_out_payments(dataset.rows)
    disputes = getattr(dataset, "disputes", {}) or {}
    # The ONLY read of `dataset.gstr2b` anywhere in this resolver, and it
    # happens here, after `resolve()` has finished every outcome that carries a
    # composition. `EvidenceKind.GST_DOCUMENT` attests to ROW EXISTENCE and
    # nothing else, so it must never reach a Verified/Ambiguous/Determinate/
    # Reconstructed/AttestationDiscrepancy -- and structurally it cannot,
    # because none of them is constructed downstream of this call.
    at_risk = _itc_risk_months(dataset)
    rows_by_id = {row["entity_id"]: row for row in dataset.rows}

    proven: dict[ProvenUnmatchedReason, list[str]] = defaultdict(list)
    breaks: dict[tuple, list[str]] = defaultdict(list)

    for row in dataset.rows:
        row_id = row["entity_id"]
        if row_id in consumed:
            continue
        entailed = _proven_reason(row, netted)
        if entailed is not None:
            proven[entailed].append(row_id)
            continue
        reason, caused_by, provable = _break_reason(
            row, horizon, blocked.get(row_id), disputes)
        age_days, seen = _age(row, horizon)
        breaks[(reason, caused_by, provable, age_days, seen)].append(row_id)

    out: list = []
    for reason, row_ids in sorted(proven.items(), key=lambda kv: kv[0].value):
        out.append(ProvenUnmatched(
            row_ids=tuple(sorted(row_ids)), reason=reason,
            warrant=Warrant.over(
                [Evidence(kind=EvidenceKind.ARITHMETIC_CLOSURE,
                          derived_from=PSP,
                          detail=_ENTAILMENT[reason])],
                rationale="the ledger entails that this money never reached "
                          "the bank; this is a claim, and G9 gates it")))
    for (reason, caused_by, provable, age_days, seen), row_ids in sorted(
            breaks.items(), key=lambda kv: (kv[0][0].value, kv[0][1] or -1,
                                            kv[0][4])):
        # Per row, not per break, and gated TWICE.
        #
        # `_month(...) in at_risk` alone is not sufficient and sec 60 measured
        # exactly how insufficient: 4 flagged rows on the spine dataset, 4 of
        # them false, precision 0.0. All four had never settled. A month is at
        # risk on behalf of the population that actually accrued fees in it,
        # and a row that accrued nothing does not acquire that month's exposure
        # by sharing a calendar with it -- it has no input tax to lose. So the
        # row must clear `_accrues_input_tax` on its OWN account, the same
        # predicate `_fee_accrual` used to decide the month was at risk in the
        # first place. See sec 61.
        #
        # The per-row loop itself stays for the reason it was written: these
        # rows share a `first_seen` and so today share a month, but that is a
        # property of the grouping key and not a guarantee, and assuming
        # all-or-nothing would silently flag clean rows the day the key changes.
        flagged = sorted(row_id for row_id in row_ids
                         if _accrues_input_tax(rows_by_id[row_id])
                         and _month(rows_by_id[row_id]) in at_risk)
        found: set[str] = set()
        for row_id in flagged:
            found.update(at_risk[_month(rows_by_id[row_id])])
        out.append(OpenBreak(
            row_ids=tuple(sorted(row_ids)), reason=reason, age_days=age_days,
            first_seen=seen, caused_by=caused_by,
            provable_within_window=provable,
            itc_risk=frozenset(flagged),
            itc_risk_grounds=tuple(sorted(found))))
    return out


_ENTAILMENT = {
    ProvenUnmatchedReason.NOT_CAPTURED:
        "the recon feed records credit = 0: the payment was never captured, "
        "so no money ever existed to reach a bank account",
    ProvenUnmatchedReason.NETTED_OUT:
        "the refunds against this payment sum EXACTLY to its gross amount and "
        "every one of them was created at or before eligible_at, so payment "
        "and refunds annihilate and neither leg is ever paid out "
        "(SETTLEMENT_SPEC.md sec 3)",
}
