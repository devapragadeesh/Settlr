"""Accounting closure and rule fidelity. SETTLEMENT_SPEC.md sec 1.2."""

from collections import defaultdict


def _paise(rupee_string: str) -> int:
    """Parse a rupee string to integer paise without touching a float."""
    sign = -1 if rupee_string.startswith("-") else 1
    whole, _, frac = rupee_string.lstrip("-").partition(".")
    return sign * (int(whole) * 100 + int((frac + "00")[:2]))


def test_every_batch_closes_with_zero_residual(rows, truth, bank):
    """Sigma(credit) - Sigma(debit) over a settlement_id == the bank credit."""
    ledger = defaultdict(lambda: [0, 0])
    for row in rows:
        if not row["settlement_id"]:
            continue
        ledger[row["settlement_id"]][0] += row["credit"]
        ledger[row["settlement_id"]][1] += row["debit"]

    # one bank line has its UTR column blanked by design, so fall back to date
    bank_by_utr = {b["utr"]: _paise(b["amount"]) for b in bank if b["utr"]}
    bank_by_date = {b["date"]: _paise(b["amount"]) for b in bank}
    assert len(ledger) == len(bank) == 12

    for batch in truth["batches"]:
        credit, debit = ledger[batch["settlement_id"]]
        assert credit == batch["credit_total"]
        assert debit == batch["debit_total"]
        assert credit - debit == batch["bank_payout"]
        printed = bank_by_utr.get(batch["utr"], bank_by_date[batch["formed_on"]])
        assert printed == batch["bank_payout"], batch["settlement_id"]


def test_no_batch_exceeds_live_balance_at_its_formation_time(truth):
    """The rule constrains the SELECTED PAYMENTS' credit, not the credit
    column (which also carries credit-side adjustments). SETTLEMENT_SPEC 1.2."""
    binding, negative = 0, 0
    for batch in truth["batches"]:
        cap = batch["available_live_balance"]
        if cap < 0:
            # live balance can legitimately go negative when debits exceed
            # credits; nothing may then be selected at all
            negative += 1
            assert batch["selected_payment_credit"] == 0, batch["settlement_id"]
            continue
        assert batch["selected_payment_credit"] <= cap, batch["settlement_id"]
        if batch["selected_payment_credit"] == cap:
            binding += 1
    assert binding >= 2, "the live-balance cap never binds -- class 5/7 are vacuous"
    assert negative >= 1, "live balance never goes negative -- sec 1.4 is untested"


def test_the_negative_payout_deferral_rule_is_exercised_by_the_data(truth):
    """SETTLEMENT_SPEC.md sec 1.4 defines a rule for a batch whose debits
    exceed its settleable credit. A rule that never fires is a rule that was
    never tested."""
    deferred = [entity for entity, reason in truth["unsettled_reason"].items()
                if reason == "debit_deferred_past_horizon"]
    assert deferred, "no debit was ever deferred -- sec 1.4 is dead code"


def test_no_batch_pays_out_a_negative_amount(truth):
    for batch in truth["batches"]:
        assert batch["bank_payout"] >= 0, batch["settlement_id"]


def test_credit_equals_amount_minus_fee_on_every_payment_row(rows):
    for row in rows:
        if row["type"] != "payment" or row["fee"] is None:
            continue
        assert row["credit"] == row["amount"] - row["fee"], row["entity_id"]


def test_refund_and_adjustment_rows_are_pure_debits_or_credits(rows):
    for row in rows:
        if row["type"] == "refund":
            assert row["debit"] == row["amount"] and row["credit"] == 0
            assert row["fee"] == 0 and row["tax"] == 0
        elif row["type"] == "adjustment":
            assert (row["debit"] == 0) != (row["credit"] == 0) or row["amount"] == 0
            assert row["debit"] + row["credit"] == row["amount"]


def test_refunds_never_exceed_their_payment(rows):
    amounts = {r["entity_id"]: r["amount"] for r in rows if r["type"] == "payment"}
    refunded = defaultdict(int)
    for row in rows:
        if row["type"] == "refund":
            refunded[row["payment_id"]] += row["amount"]
    for payment_id, total in refunded.items():
        assert total <= amounts[payment_id], payment_id


def test_a_refund_never_settles_before_its_own_creation(rows):
    for row in rows:
        if row["settled_at"]:
            assert row["settled_at"] >= row["created_at"], row["entity_id"]


def test_every_excluded_payment_is_accounted_for(rows, truth):
    """Roll-forward: nothing vanishes. Every unsettled row has a stated reason."""
    reasons = truth["unsettled_reason"]
    valid = {
        "not_captured", "netted_out_by_full_refund", "on_hold_dispute",
        "not_yet_eligible_at_horizon", "rolled_forward_past_horizon",
        "debit_deferred_past_horizon",
    }
    for row in rows:
        if row["settled"]:
            assert row["entity_id"] not in reasons, row["entity_id"]
        else:
            assert reasons[row["entity_id"]] in valid, row["entity_id"]


def test_a_rolled_forward_payment_really_does_appear_in_a_later_batch(rows, truth):
    order = {b["settlement_id"]: i for i, b in enumerate(truth["batches"])}
    rolled = [e for e, classes in truth["row_classes"].items()
              if "c05_subset_sum_rolled_forward" in classes]
    assert len(rolled) >= 5, "class 5 is under-represented"
    by_id = {r["entity_id"]: r for r in rows}
    for entity_id in rolled:
        row = by_id[entity_id]
        assert row["settled"], entity_id
        assert order[row["settlement_id"]] > 0


def test_netted_out_payments_and_their_refunds_both_stay_unsettled(rows, truth):
    netted = set(truth["netted_out"])
    assert netted, "class 2 (full refund pre-settlement) is missing"
    by_id = {r["entity_id"]: r for r in rows}
    for payment_id in netted:
        assert by_id[payment_id]["settled"] is False
        for row in rows:
            if row["type"] == "refund" and row["payment_id"] == payment_id:
                assert row["settled"] is False, row["entity_id"]


def test_held_payments_are_absent_from_every_batch(rows):
    for row in rows:
        if row["on_hold"]:
            assert row["settled"] is False
            assert row["settlement_id"] is None
