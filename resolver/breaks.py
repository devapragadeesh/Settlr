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
        out.append(OpenBreak(
            row_ids=tuple(sorted(row_ids)), reason=reason, age_days=age_days,
            first_seen=seen, caused_by=caused_by,
            provable_within_window=provable))
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
