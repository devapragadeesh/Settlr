"""Simulator rule fidelity. SETTLEMENT_SPEC.md sec 1-3."""

import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from simulator import (  # noqa: E402
    add_working_days, ceil_div, compute_fee, max_subsets_under_cap,
)


# --- the documented worked example -----------------------------------------

def test_reproduces_razorpays_own_worked_example():
    """P1 500, P2 300, P3 200; a 100 refund drops live balance to 900.

    Razorpay says P1 and P2 settle. Only the "maximal subset under a cap"
    reading produces that answer -- SETTLEMENT_SPEC.md sec 1.1.
    """
    best, subsets, truncated = max_subsets_under_cap(
        [("P1", 500), ("P2", 300), ("P3", 200)], 900)
    assert best == 800
    assert subsets == [("P1", "P2")]
    assert truncated is False


def test_exact_equality_reading_would_be_unsatisfiable():
    """No subset of {500,300,200} equals 900 -- reading (A) is rejected."""
    sums = {0}
    for value in (500, 300, 200):
        sums |= {s + value for s in sums}
    assert 900 not in sums


# --- subset-sum engine ------------------------------------------------------

def test_enumerates_every_tying_subset():
    best, subsets, truncated = max_subsets_under_cap(
        [("a", 60), ("b", 55), ("c", 45), ("d", 40)], 100)
    assert best == 100
    assert subsets == [("a", "d"), ("b", "c")]
    assert truncated is False


def test_never_exceeds_the_cap():
    # near-powers-of-two keep the number of tying subsets small
    items = [(chr(97 + i), 2 ** i * 100 + i) for i in range(12)]
    for cap in range(0, 400000, 4099):
        best, subsets, _truncated = max_subsets_under_cap(items, cap)
        assert best <= cap
        for subset in subsets:
            assert sum(dict(items)[name] for name in subset) == best


def test_is_order_independent():
    items = [("a", 60), ("b", 55), ("c", 45), ("d", 40)]
    assert (max_subsets_under_cap(items, 100)
            == max_subsets_under_cap(list(reversed(items)), 100))


# --- fee model --------------------------------------------------------------

def test_fee_model_reproduces_every_captured_row(captured):
    """14/14 exact, to the paise. SETTLEMENT_SPEC.md sec 4.1."""
    checked = 0
    for payment in captured["payments"]:
        if payment["fee"] is None:
            continue
        fee, tax = compute_fee(payment["amount"], payment["method"])
        assert (fee, tax) == (payment["fee"], payment["tax"]), payment["id"]
        checked += 1
    assert checked == 14


def test_fee_is_inclusive_of_tax_on_captured_data(captured):
    """The balance identity closes with zero residual under credit = amount - fee."""
    payments = captured["payments"]
    expected = sum(p["amount"] - p["fee"] for p in payments if p["fee"] is not None)
    expected -= sum(r["amount"] for r in captured["refunds"])
    assert expected == captured["balance"]["balance"]

    wrong = sum(p["amount"] - p["fee"] - p["tax"]
                for p in payments if p["fee"] is not None)
    wrong -= sum(r["amount"] for r in captured["refunds"])
    assert wrong != captured["balance"]["balance"]


def test_upi_is_billed_at_the_same_platform_fee_as_every_other_method():
    """Zero-MDR under Sec 269SU binds banks and system providers, NOT the
    aggregator's platform fee -- and Razorpay's published pricing bills UPI at
    2%. Claiming UPI is free would contradict the vendor's own price list."""
    assert compute_fee(500000, "upi") == compute_fee(500000, "netbanking")
    assert compute_fee(500000, "upi")[0] > 0


def test_amex_and_diners_are_priced_at_three_percent():
    fee, tax = compute_fee(100000, "card", "Amex", "credit")
    assert fee - tax == 3000                       # 3% of 100000 paise
    assert compute_fee(100000, "card", "Diners", "credit") == (fee, tax)
    assert compute_fee(100000, "card", "Visa", "credit")[0] < fee


def test_rupay_debit_carries_zero_mdr():
    """Statutory (Sec 269SU IT Act / Sec 10A PSS Act), not from Razorpay's
    published table, which does not itemise it. Tier synthesized_modelled."""
    assert compute_fee(100000, "card", "RuPay", "debit") == (0, 0)
    assert compute_fee(100000, "card", "RuPay", "credit")[0] > 0


def test_a_tax_free_row_reproduces_the_published_sample_shape():
    """Razorpay's own recon sample: amount 100000, fee 2900, tax 0."""
    fee, tax = compute_fee(100000, "card", "Visa", "credit", gst_applies=False)
    assert tax == 0 and fee > 0


def test_fifo_reading_is_available_as_a_swappable_rule():
    from simulator import SELECTION_RULES, fifo_under_cap
    assert set(SELECTION_RULES) == {"max_under_cap", "fifo_under_cap"}
    # oldest-first greedy: skips the item that would breach, keeps filling
    total, subsets, _truncated = fifo_under_cap(
        [("a", 500), ("b", 600), ("c", 300)], 900)
    assert (total, subsets) == (800, [("a", "c")])
    assert len(subsets) == 1, "the FIFO reading is never ambiguous"


def test_ceil_div_is_exact_and_floatless():
    assert ceil_div(1528 * 18, 100) == 276      # the captured 76400 row
    assert ceil_div(-7, 2) == -3
    assert isinstance(ceil_div(3, 2), int)


# --- T+2 -------------------------------------------------------------------

def test_tplus2_skips_weekends():
    import datetime as dt
    from simulator import IST
    friday = int(dt.datetime(2026, 6, 19, 11, 0, tzinfo=IST).timestamp())
    landed = dt.datetime.fromtimestamp(add_working_days(friday, 2, 17), IST)
    assert landed.strftime("%Y-%m-%d %H:%M") == "2026-06-23 17:00"   # Tuesday
    assert landed.weekday() < 5


def test_a_degenerate_pool_reports_truncation_rather_than_lying_or_crashing():
    """Twenty identical payments admit C(20,10) tying subsets. Returning a
    partial list as if complete would be a ground-truth lie; raising would
    pretend the case does not exist. It reports truncation instead."""
    items = [(f"p{i:02d}", 100) for i in range(20)]
    best, subsets, truncated = max_subsets_under_cap(items, 1000)
    assert best == 1000
    assert truncated is True
    assert len(subsets) > 1


def test_the_fifo_reading_never_reports_truncation():
    from simulator import fifo_under_cap
    items = [(f"p{i:02d}", 100) for i in range(20)]
    _best, subsets, truncated = fifo_under_cap(items, 1000)
    assert truncated is False and len(subsets) == 1
