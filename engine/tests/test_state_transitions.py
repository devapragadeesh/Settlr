"""Impossible lifecycle states must not exist anywhere in the dataset."""

from collections import defaultdict


def _payments(rows):
    return [r for r in rows if r["type"] == "payment"]


def test_a_refund_never_predates_its_payment(rows):
    created = {r["entity_id"]: r["created_at"] for r in _payments(rows)}
    for row in rows:
        if row["type"] == "refund":
            assert row["created_at"] >= created[row["payment_id"]], row["entity_id"]


def test_nothing_settles_before_it_was_created(rows):
    for row in rows:
        if row["settled_at"] is not None:
            assert row["settled_at"] >= row["created_at"], row["entity_id"]


def test_nothing_settles_in_a_batch_formed_before_the_row_existed(rows, truth):
    formed = {b["settlement_id"]: b["formed_at"] for b in truth["batches"]}
    for row in rows:
        if row["settlement_id"]:
            assert formed[row["settlement_id"]] >= row["created_at"], row["entity_id"]
            assert row["settled_at"] == formed[row["settlement_id"]]


def test_a_payment_never_settles_before_its_t_plus_two_eligibility(rows, truth):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from simulator import add_working_days
    for row in _payments(rows):
        if row["settled_at"]:
            assert row["settled_at"] >= add_working_days(row["created_at"], 2, 17), \
                row["entity_id"]


def test_an_uncaptured_payment_never_settles_and_never_has_a_refund(rows):
    uncaptured = {r["entity_id"] for r in _payments(rows) if r["fee"] is None}
    assert uncaptured
    for row in rows:
        if row["entity_id"] in uncaptured:
            assert row["settled"] is False
            assert row["credit"] == 0
        if row["type"] == "refund":
            assert row["payment_id"] not in uncaptured, row["entity_id"]


def test_a_dispute_never_opens_on_an_uncaptured_payment(rows, disputes):
    uncaptured = {r["entity_id"] for r in _payments(rows) if r["fee"] is None}
    for dispute in disputes:
        assert dispute["payment_id"] not in uncaptured


def test_at_most_one_dispute_per_payment(disputes):
    seen = defaultdict(int)
    for dispute in disputes:
        seen[dispute["payment_id"]] += 1
    assert all(count == 1 for count in seen.values())


def test_a_won_or_lost_dispute_is_never_still_on_hold(rows, disputes):
    by_payment = {d["payment_id"]: d for d in disputes}
    for row in _payments(rows):
        dispute = by_payment.get(row["entity_id"])
        if dispute and dispute["status"] in ("won", "lost"):
            assert row["on_hold"] is False, row["entity_id"]
        if dispute and dispute["status"] == "under_review":
            assert row["on_hold"] is True, row["entity_id"]


def test_a_won_dispute_releases_its_hold(rows, disputes, truth):
    """The hold must clear. Whether the released payment then settles before
    the observation horizon is a separate question -- one that legitimately
    rolls forward, and the ground-truth key says which."""
    won = [d for d in disputes if d["status"] == "won"]
    assert won, "class 10 is missing"
    by_id = {r["entity_id"]: r for r in _payments(rows)}
    settled_later = 0
    for dispute in won:
        row = by_id[dispute["payment_id"]]
        assert row["on_hold"] is False, dispute["payment_id"]
        if row["settled"]:
            assert row["settled_at"] > dispute["created_at"]
            settled_later += 1
        else:
            assert truth["unsettled_reason"][row["entity_id"]] \
                == "rolled_forward_past_horizon"
    assert settled_later >= 2, "class 10 needs at least two settled instances"


def test_a_held_payments_credit_is_excluded_from_live_balance(rows, truth):
    """Held funds are locked, so they must not appear in any batch."""
    held = [r for r in _payments(rows) if r["on_hold"]]
    assert held, "class 8 is missing"
    for row in held:
        assert row["settlement_id"] is None
        assert truth["unsettled_reason"][row["entity_id"]] == "on_hold_dispute"


def test_a_lost_dispute_produces_exactly_one_unjoinable_adjustment(rows, disputes):
    lost = {d["id"] for d in disputes if d["status"] == "lost"}
    assert lost, "class 9 is missing"
    adjustments = [r for r in rows
                   if r["type"] == "adjustment" and r["dispute_id"] in lost]
    assert len(adjustments) == len(lost)
    for row in adjustments:
        assert row["debit"] == row["amount"] > 0
        assert row["payment_id"] is None and row["order_id"] is None
        assert row["method"] is None


def test_a_lost_dispute_adjustment_never_predates_the_dispute(rows, disputes):
    opened = {d["id"]: d["created_at"] for d in disputes}
    for row in rows:
        if row["type"] == "adjustment" and row["dispute_id"]:
            assert row["created_at"] >= opened[row["dispute_id"]], row["entity_id"]


def test_a_payment_appears_in_at_most_one_batch(rows):
    seen = defaultdict(set)
    for row in rows:
        if row["settlement_id"]:
            seen[row["entity_id"]].add(row["settlement_id"])
    assert all(len(v) == 1 for v in seen.values())


def test_a_fully_refunded_payment_never_settles(rows):
    amounts = {r["entity_id"]: r["amount"] for r in _payments(rows)}
    refunded = defaultdict(int)
    for row in rows:
        if row["type"] == "refund":
            refunded[row["payment_id"]] += row["amount"]
    by_id = {r["entity_id"]: r for r in _payments(rows)}
    full = [p for p, total in refunded.items() if total == amounts[p]]
    assert full, "class 2 is missing"
    for payment_id in full:
        # a payment fully refunded BEFORE it settled nets out; one refunded
        # after settling has already been paid out and stays settled
        row = by_id[payment_id]
        refunds = [r for r in rows
                   if r["type"] == "refund" and r["payment_id"] == payment_id]
        if not row["settled"]:
            assert all(not r["settled"] for r in refunds), payment_id


def test_wallet_and_netbanking_rows_carry_no_card_metadata(rows):
    for row in rows:
        if row["method"] in ("wallet", "netbanking", "upi"):
            assert row["card_network"] is None
            assert row["card_issuer"] is None
            assert row["card_type"] is None


def test_created_at_stays_inside_the_generation_window(rows):
    from datetime import datetime, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    low = int(datetime(2026, 6, 15, tzinfo=ist).timestamp())
    high = int(datetime(2026, 9, 3, tzinfo=ist).timestamp())
    for row in rows:
        assert low <= row["created_at"] <= high, row["entity_id"]
