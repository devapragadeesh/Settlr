"""Metrics are only worth reporting if their definitions are pinned."""

import pytest

from eval.metrics import Accounting, MatchMetrics


def test_row_accounting_partitions_every_row(scored, dataset):
    _match, _ambiguity, accounting = scored
    assert accounting.total_rows == len(dataset.rows) == 240
    assert accounting.partitions, "buckets overlap or leave rows out"
    assert accounting.truly_settled + accounting.truly_unsettled == 240


def test_match_rate_denominator_excludes_only_unmatchable_rows(scored, truth):
    _match, _ambiguity, accounting = scored
    truly_settled = sum(1 for row_id in truth["settled_in"])
    assert accounting.truly_settled == truly_settled
    assert accounting.truly_unsettled == len(truth["unsettled_reason"])


def test_match_rate_is_below_one_hundred_percent(scored):
    """A claimed 100% reads as a bug or a lie. Rows in provably ambiguous
    batches are correctly declined and correctly count against the rate."""
    _match, _ambiguity, accounting = scored
    assert 0.90 <= accounting.match_rate < 1.0
    assert accounting.declined_as_ambiguous > 0


def test_precision_and_recall_exclude_ambiguous_batches(scored):
    match, _ambiguity, _accounting = scored
    assert match.excluded_ambiguous > 0
    assert match.scored_rows + match.excluded_ambiguous > 190


def test_precision_falls_when_a_wrong_assignment_is_injected():
    """A metric that cannot go down is not measuring anything."""
    metrics = MatchMetrics(true_positives=90, false_positives=10,
                           false_negatives=0, scored_rows=100)
    assert metrics.precision == pytest.approx(0.9)
    assert metrics.recall == 1.0
    assert metrics.f1 == pytest.approx(0.9473, abs=1e-4)


def test_recall_falls_when_matches_are_missed():
    metrics = MatchMetrics(true_positives=80, false_positives=0,
                           false_negatives=20, scored_rows=80)
    assert metrics.precision == 1.0
    assert metrics.recall == pytest.approx(0.8)


def test_a_match_everything_solver_would_be_caught_by_precision():
    metrics = MatchMetrics(true_positives=203, false_positives=37,
                           false_negatives=0, scored_rows=240)
    assert metrics.recall == 1.0
    assert metrics.precision < 0.85, "precision must punish indiscriminate matching"


def test_itc_at_risk_is_reported_in_rupees_and_covers_three_grounds(cascade):
    tax = cascade.stage4.tax
    assert tax.itc_at_risk_paise > 0
    grounds = {line["reason"] for line in tax.itc_lines}
    assert grounds == {"gstr2b_absent", "gstr2b_no_irn", "gstr2b_37a_exposure"}
    from matching.money import inr
    assert inr(tax.itc_at_risk_paise).startswith("₹")


def test_the_supplier_gstin_is_identified_not_assumed(cascade, truth):
    """Nothing labels which 2B supplier is the gateway. It is found by tying
    invoice taxable values to the fee actually deducted."""
    assert cascade.stage4.tax.supplier_gstin == truth["razorpay_gstin"]


def test_gst_rounding_residuals_are_reported_and_within_tolerance(cascade):
    residuals = cascade.stage4.tax.rounding_residuals
    assert residuals
    for item in residuals:
        assert item["residual_paise"] != 0
        assert item["within_tolerance"], item


def test_fee_charged_without_gst_is_surfaced_separately(cascade):
    tax = cascade.stage4.tax
    assert tax.fee_charged_without_gst_paise > 0
    assert tax.fee_without_gst_rows


def test_every_exception_type_required_by_the_brief_is_representable():
    from matching.stage4_exceptions import OWNERS
    required = {
        "subset_sum_rolled_forward", "not_yet_eligible", "dispute_hold_pending",
        "lost_dispute_adjustment", "netted_out_by_full_refund",
        "erp_gap_no_order", "erp_gap_no_payment", "gstr2b_absent",
        "gstr2b_no_irn", "gstr2b_37a_exposure", "genuinely_unresolved",
    }
    assert required <= set(OWNERS)


def test_pending_states_are_not_counted_as_actionable_exceptions(cascade):
    from matching.stage4_exceptions import NOT_A_PROBLEM
    for item in cascade.stage4.exceptions:
        if item.type in NOT_A_PROBLEM:
            assert not item.is_actionable
            assert item.owner == "no-action"


def test_genuinely_unresolved_is_near_zero(cascade):
    unresolved = [e for e in cascade.stage4.exceptions
                  if e.type == "genuinely_unresolved"]
    assert len(unresolved) == 0


def test_every_exception_carries_the_required_fields(cascade):
    for item in cascade.stage4.exceptions:
        assert item.type and item.entity_id and item.owner
        assert isinstance(item.evidence, dict) and item.evidence
        assert 0.0 < item.confidence <= 1.0
        assert item.narrative
