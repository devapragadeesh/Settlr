"""A matcher that pairs everything scores 100% recall and is worthless.

These are the tests that separate the two. They assert the engine did NOT match
things that have no partner -- which costs match rate and is the correct
outcome.
"""

import pytest

from matching.loaders import is_unjoinable_adjustment


def test_erp_gap_payments_are_never_given_an_invoice(cascade, truth):
    """Some settled payments genuinely have no ERP order. That is a control
    failure to report, not a pair to invent."""
    missing = set(truth["payments_missing_from_erp"])
    assert missing
    matched_to_erp = set(cascade.stage1.row_to_erp) | set(cascade.stage3.erp_assignments)
    assert not (missing & matched_to_erp)


def test_orphan_erp_invoices_are_never_given_a_payment(cascade, truth):
    orphans = set(truth["erp_orphan_invoices"])
    assert orphans
    used = set(cascade.stage1.row_to_erp.values()) | set(
        cascade.stage3.erp_assignments.values())
    assert not (orphans & used)


def test_lost_dispute_adjustments_are_never_given_a_counterparty(cascade, dataset):
    """No payment_id, no order_id, no method -- unjoinable BY CONSTRUCTION.
    A matcher that finds a partner for one has produced a false positive."""
    unjoinable = [row for row in dataset.rows if is_unjoinable_adjustment(row)]
    assert unjoinable
    matched_to_erp = set(cascade.stage1.row_to_erp) | set(cascade.stage3.erp_assignments)
    for row in unjoinable:
        assert row["entity_id"] not in matched_to_erp
        assert row["payment_id"] is None
        assert row["order_id"] is None
        assert row["method"] is None


def test_lost_dispute_adjustments_still_reach_the_exception_queue(cascade, dataset):
    """Unjoinable to a COUNTERPARTY is not the same as unplaced in a BATCH.
    They are debit rows and the balance identity needs them, so they are
    reported either way."""
    reported = {item.entity_id for item in cascade.stage4.exceptions
                if item.type == "lost_dispute_adjustment"}
    expected = {row["entity_id"] for row in dataset.rows
                if is_unjoinable_adjustment(row) and row["dispute_id"]}
    assert expected
    assert expected == reported


def test_the_hungarian_stage_assigns_nothing_and_refuses_explicitly(cascade):
    """`linear_sum_assignment` returns a COMPLETE matching whether or not the
    pairs make sense. The cost gate is the only thing between the optimiser and
    a full set of false positives, and the refusals prove it looked."""
    assert cascade.stage3.erp_assignments == {}
    assert len(cascade.stage3.erp_rejected) > 0
    from matching.stage3_solver import HUNGARIAN_REJECT_COST
    for _left, _right, cost in cascade.stage3.erp_rejected:
        assert cost > HUNGARIAN_REJECT_COST


def test_fuzzy_blocking_proposed_erp_pairs_and_the_gate_refused_them(cascade):
    """An engine that never looked and one that looked and refused produce the
    same empty assignment. The refusals are how they are told apart."""
    erp_rejections = [item for item in cascade.stage2.rejected
                      if "identifier" in item.reason]
    assert erp_rejections, "blocking proposed nothing -- the gate is untested"
    for item in erp_rejections:
        assert "amount_and_date_are_not_identity" in item.reason


def test_no_row_is_placed_in_a_batch_it_does_not_belong_to(scored):
    _match, _ambiguity, accounting = scored
    assert accounting.placed_incorrectly == 0


def test_no_row_that_never_settles_is_placed_anywhere(scored):
    _match, _ambiguity, accounting = scored
    assert accounting.wrongly_placed == 0
    assert accounting.correctly_left_unmatched == accounting.truly_unsettled


def test_precision_is_reported_alongside_recall(scored):
    """Recall alone is not a bar; a matcher that matches everything clears it."""
    match, _ambiguity, _accounting = scored
    assert match.precision == 1.0
    assert match.recall == 1.0
    assert match.scored_rows > 100


def test_dispute_held_rows_are_blocked_not_matched(cascade, dataset):
    held = [row for row in dataset.rows if row["on_hold"]]
    assert held
    for row in held:
        assert row["entity_id"] not in cascade.stage3.assigned
    reported = {item.entity_id for item in cascade.stage4.exceptions
                if item.type == "dispute_hold_pending"}
    assert reported == {row["entity_id"] for row in held}
