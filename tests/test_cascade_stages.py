"""Stage-by-stage behaviour and the cumulative match rate."""

import pytest


def test_stage1_joins_on_settlement_id_not_utr(cascade, dataset):
    """Grouping on `settlement_utr` silently drops adjustment rows, which carry
    a real settlement_id with a NULL utr -- so the batch would appear not to
    close and the engine would report a discrepancy on correct data."""
    adjustments_in_batches = 0
    for settlement_id, batch in cascade.stage1.batches.items():
        for row_id in batch.row_ids:
            row = next(r for r in dataset.rows if r["entity_id"] == row_id)
            if row["type"] == "adjustment":
                assert row["settlement_utr"] is None
                adjustments_in_batches += 1
    assert adjustments_in_batches > 0, "no adjustment is inside a batch to test with"


def test_stage1_baseline_is_reported_and_incomplete(cascade):
    """The baseline exists to prove later stages do real work."""
    contributions = cascade.stage_contributions()
    assert contributions["stage1_bank_lines"] == 10
    assert contributions["total_bank_lines"] == 12
    assert contributions["stage1_bank_lines"] < contributions["total_bank_lines"]


def test_stage2_recovers_both_unjoined_lines_for_different_reasons(cascade):
    assert cascade.stage_contributions()["stage1_plus_stage2_bank_lines"] == 12
    notes = cascade.stage2.recovery_notes
    assert len(notes) == 2
    reasons = " ".join(notes.values())
    assert "bank utr column blank" in reasons
    assert "settlement_utr null" in reasons


def test_the_blank_utr_line_is_recovered_on_amount_and_date(cascade, dataset):
    blank = [line for line in dataset.bank if not line.has_join_key]
    assert len(blank) == 1
    assert blank[0].index in cascade.stage2.bank_to_batch


def test_failed_payments_are_filtered_before_any_arithmetic(cascade, dataset):
    """fee is null, not 0. Summing null raises; coercing it invents a fee."""
    failed = [r for r in dataset.rows if r["type"] == "payment" and r["fee"] is None]
    assert failed
    for row in failed:
        assert row["tax"] is None
        assert row["entity_id"] not in cascade.stage3.assigned
        assert row["entity_id"] in cascade.stage1.failed_payment_ids


def test_id_resolution_rule_is_applied(dataset):
    from matching.loaders import resolve_row_id
    for row in dataset.rows:
        resolved = resolve_row_id(row)
        if row["type"] == "payment":
            assert resolved == row["entity_id"]
            assert row["payment_id"] is None
        else:
            assert resolved == row["payment_id"]


def test_credit_type_absence_is_detected_by_key_not_value(dataset):
    from matching.loaders import has_credit_type
    adjustments = [r for r in dataset.rows if r["type"] == "adjustment"]
    assert adjustments
    for row in adjustments:
        assert not has_credit_type(row)
        assert "credit_type" not in row
    for row in (r for r in dataset.rows if r["type"] != "adjustment"):
        assert has_credit_type(row)


def test_no_float_appears_in_any_parsed_money_value(dataset):
    for line in dataset.bank:
        assert isinstance(line.amount, int)
    for order in dataset.erp:
        assert isinstance(order.amount, int)
    for line in dataset.gstr2b:
        for value in (line.taxable_value, line.igst, line.cgst, line.sgst):
            assert isinstance(value, int)


def test_rupee_parsing_is_exact_and_rejects_junk():
    from matching.money import paise, rupees
    assert paise("1234.56") == 123456
    assert paise("0.01") == 1
    assert paise("-12.30") == -1230
    assert paise("105108.21") == 10510821
    assert rupees(10510821) == "105108.21"
    for bad in ("1.234", "abc", "", "1,234.00", "1.2.3"):
        with pytest.raises(ValueError):
            paise(bad)


def test_cumulative_match_rate_improves_through_the_stages(cascade, scored):
    _match, _ambiguity, accounting = scored
    contributions = cascade.stage_contributions()
    stage1_rows = len(cascade.stage1.matched_row_ids)
    assert stage1_rows < accounting.placed_correctly, \
        "Stage 3 placed no rows Stage 1 had not already grouped"
    assert contributions["stage3_determinate_reconstructions"] >= 9
