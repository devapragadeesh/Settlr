"""The both-hypothesis fee analyzer, and the INDECISIVE case.

The analyzer under test is deliberately naive: it is here to prove the dataset
can DISCRIMINATE between the two identities, and to prove it correctly refuses
to on degenerate rows. It is not solver logic.
"""

INCLUSIVE = "credit = amount - fee"          # verified on captured data
EXCLUSIVE = "credit = amount - fee - tax"    # the rejected identity


def analyse(row):
    """Return the set of identities consistent with this row.

    Two identities -> INDECISIVE. One -> decided. Zero -> the row is broken.
    """
    if row["fee"] is None:
        return set()
    fits = set()
    if row["credit"] == row["amount"] - row["fee"]:
        fits.add(INCLUSIVE)
    if row["credit"] == row["amount"] - row["fee"] - row["tax"]:
        fits.add(EXCLUSIVE)
    return fits


def _payment_rows(rows):
    return [r for r in rows if r["type"] == "payment" and r["fee"] is not None]


def test_inclusive_identity_holds_on_every_fee_bearing_row(rows):
    for row in _payment_rows(rows):
        assert INCLUSIVE in analyse(row), row["entity_id"]


def test_non_degenerate_rows_decide_for_the_inclusive_identity(rows):
    decisive = [r for r in _payment_rows(rows) if r["tax"] != 0]
    assert len(decisive) > 100, "not enough discriminating rows to make a claim"
    for row in decisive:
        assert analyse(row) == {INCLUSIVE}, row["entity_id"]


def test_zero_tax_rows_are_reported_indecisive_not_silently_passed(rows):
    """The two identities differ by exactly `tax`, so a row with tax == 0 is
    degenerate whatever its fee. Razorpay's own published recon sample is
    degenerate on its payment row, which is precisely why the wrong identity
    is easy to adopt. The analyzer MUST say INDECISIVE here."""
    degenerate = [r for r in _payment_rows(rows) if r["tax"] == 0]
    assert degenerate, "no zero-tax rows -- the degenerate case is missing"
    assert any(r["fee"] > 0 for r in degenerate), \
        "no tax:0 row with a non-zero fee -- the published sample shape is missing"
    assert any(r["fee"] == 0 for r in degenerate), \
        "no fully zero-rated row -- RuPay debit zero-MDR is missing"
    for row in degenerate:
        fits = analyse(row)
        assert fits == {INCLUSIVE, EXCLUSIVE}, row["entity_id"]
        assert len(fits) > 1, "an analyzer claiming a decision here is wrong"


def test_the_dataset_as_a_whole_is_decisive(rows):
    verdicts = [analyse(r) for r in _payment_rows(rows)]
    decided = [v for v in verdicts if len(v) == 1]
    indecisive = [v for v in verdicts if len(v) > 1]
    assert decided and all(v == {INCLUSIVE} for v in decided)
    assert indecisive, "a dataset with no degenerate rows cannot test INDECISIVE"


def test_percentage_rounding_leaves_sub_rupee_residuals(rows):
    """Ceiling-rounded GST produces effective tax rates just above 18%."""
    strictly_above = 0
    for row in _payment_rows(rows):
        if row["fee"] == 0 or row["tax"] == 0:
            continue
        fee_ex = row["fee"] - row["tax"]
        # 18% exactly, or up to 1 paise above it
        assert fee_ex * 18 <= row["tax"] * 100 < fee_ex * 18 + 100, row["entity_id"]
        if row["tax"] * 100 != fee_ex * 18:
            strictly_above += 1
    assert strictly_above > 0, "no rounding residuals present"


def test_every_row_sits_on_a_published_mdr_rate(rows):
    """2% domestic default; 3% Amex/Diners; 0% RuPay debit."""
    seen = set()
    for row in _payment_rows(rows):
        fee_ex = row["fee"] - row["tax"]
        if (row["card_network"], row["card_type"]) in (
                ("Amex", "credit"), ("Amex", "debit"), ("Diners", "credit")):
            rate = 3
        elif (row["card_network"], row["card_type"]) == ("RuPay", "debit"):
            assert row["fee"] == 0, row["entity_id"]
            seen.add(0)
            continue
        else:
            rate = 2
        assert row["amount"] * rate <= fee_ex * 100 < row["amount"] * rate + 100, \
            (row["entity_id"], row["method"], row["card_network"], row["card_type"])
        seen.add(rate)
    assert seen == {0, 2, 3}, f"MDR tiers exercised: {sorted(seen)}"


def test_upi_is_never_free(rows):
    upi = [r for r in _payment_rows(rows) if r["method"] == "upi"]
    assert upi
    for row in upi:
        assert row["fee"] > 0, row["entity_id"]
