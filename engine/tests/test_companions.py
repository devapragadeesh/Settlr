"""Bank statement, ERP and GSTR-2B companions must be reconcilable -- and
lossy in exactly the ways they are meant to be."""

import re
from collections import Counter


def _paise(value: str) -> int:
    sign = -1 if value.startswith("-") else 1
    whole, _, frac = value.lstrip("-").partition(".")
    return sign * (int(whole) * 100 + int((frac + "00")[:2]))


MONEY = re.compile(r"^-?\d+\.\d{2}$")


# --- bank statement --------------------------------------------------------

def test_one_bank_credit_per_settlement(bank, truth):
    assert len(bank) == len(truth["batches"]) == 12
    printed = {b["utr"] for b in bank} - {""}
    assert printed < {b["utr"] for b in truth["batches"]}
    assert len(printed) == 11


def test_bank_amounts_are_exact_rupee_strings(bank):
    for line in bank:
        assert MONEY.match(line["amount"]), line["amount"]
        assert _paise(line["amount"]) >= 0


def test_bank_amount_equals_the_batch_payout(bank, truth):
    payout = {b["utr"]: b["bank_payout"] for b in truth["batches"]}
    by_date = {b["formed_on"]: b["bank_payout"] for b in truth["batches"]}
    for line in bank:
        expected = payout[line["utr"]] if line["utr"] else by_date[line["date"]]
        assert _paise(line["amount"]) == expected


def test_a_subset_of_narrations_is_deliberately_lossy(bank, truth):
    corrupt = set(truth["corrupt_bank_narration_batch_index"])
    assert corrupt, "class 14 is missing"
    recoverable, lossy = 0, 0
    for index, line in enumerate(bank):
        if line["utr"] and line["utr"] in line["narration"]:
            recoverable += 1
        else:
            lossy += 1
            assert index in corrupt, f"row {index} is lossy but not labelled"
    assert lossy >= 2 and recoverable >= 6


def test_exactly_one_bank_row_has_no_join_key_at_all(bank, truth):
    """On one line the UTR column itself is gone, not merely damaged inside
    free text. A matcher must fall back to (amount, date) for that row."""
    blank = [i for i, line in enumerate(bank) if not line["utr"]]
    assert blank == [truth["blanked_utr_bank_row_index"]]
    assert blank[0] in truth["corrupt_bank_narration_batch_index"]

    known = {b["utr"] for b in truth["batches"]}
    for index, line in enumerate(bank):
        if index in blank:
            continue
        assert line["utr"] in known

    # the fallback must actually be sufficient: (amount, date) is unique here
    keys = [(line["amount"], line["date"]) for line in bank]
    assert len(set(keys)) == len(keys), "the (amount, date) fallback is ambiguous"


# --- ERP -------------------------------------------------------------------

def test_erp_joins_to_orders_but_not_completely(erp, rows, truth):
    order_ids = {r["order_id"] for r in rows if r["type"] == "payment"}
    erp_ids = {row["order_id"] for row in erp}
    matched = erp_ids & order_ids
    assert matched, "ERP does not join to the recon data at all"
    assert erp_ids - order_ids, "no orphan ERP orders planted"
    assert order_ids - erp_ids, "no payments missing from ERP planted"
    assert len(truth["payments_missing_from_erp"]) >= 5
    assert len(truth["erp_orphan_invoices"]) >= 3


def test_erp_amounts_match_the_payment_amount_where_they_join(erp, rows):
    amounts = {r["order_id"]: r["amount"] for r in rows if r["type"] == "payment"}
    joined = 0
    for line in erp:
        if line["order_id"] in amounts:
            assert _paise(line["amount"]) == amounts[line["order_id"]], line["invoice_no"]
            joined += 1
    assert joined > 100


def test_erp_invoice_numbers_are_unique(erp):
    numbers = [line["invoice_no"] for line in erp]
    assert len(set(numbers)) == len(numbers)


def test_erp_gstins_pass_the_mod36_checksum(erp):
    """Checksum-valid is not the same as issuable. Every generated GSTIN
    deliberately carries an INVALID PAN entity-type character in position 4,
    which guarantees it cannot collide with a real registration while still
    passing the standard regex and check digit."""
    from generator import gstin_checksum
    seen = 0
    for line in erp:
        gstin = line["gstin"]
        if not gstin:
            continue                      # B2C order, no customer GSTIN
        assert len(gstin) == 15, gstin
        assert gstin_checksum(gstin[:14]) == gstin[14], gstin
        # GSTIN = 2 state digits + 10-char PAN; the PAN entity-type
        # character is the 4th PAN letter, i.e. index 5 overall
        assert gstin[5] not in "ABCFGHLJPTKE", "PAN entity char is issuable"
        seen += 1
    assert seen > 5


def test_most_erp_orders_are_b2c_and_carry_no_customer_gstin(erp):
    blank = sum(1 for line in erp if not line["gstin"])
    assert blank * 100 // len(erp) > 60, "an all-B2B retail book is unrealistic"


def test_no_generated_gstin_is_razorpays_real_one(erp, gstr2b, truth):
    real = "29AAGCR4375J1ZU"
    assert truth["razorpay_gstin"] != real
    assert truth["merchant_gstin"] != real
    for line in erp + gstr2b:
        assert line["gstin"] != real


# --- GSTR-2B ---------------------------------------------------------------

def _razorpay_lines(gstr2b, truth):
    return [r for r in gstr2b if r["gstin"] == truth["razorpay_gstin"]]


def test_razorpay_issues_one_consolidated_invoice_per_month(gstr2b, truth):
    """Razorpay deducts per settlement but invoices monthly, so ONE 2B line
    must tie back to N settlements' fee columns."""
    lines = _razorpay_lines(gstr2b, truth)
    assert lines, "no Razorpay fee invoice in 2B -- there is no ITC to test"
    periods = [line["invoice_date"][:7] for line in lines]
    assert len(set(periods)) == len(periods), "more than one invoice per month"
    # only months in which fee-bearing payments actually settled produce an
    # invoice -- a batch of pure adjustments generates no Razorpay fee
    fee_periods = {r["period"] for r in truth["gst_rounding_residuals"]}
    fee_periods |= {e["period"] for e in truth["itc_at_risk"]}
    fee_periods |= {line["gstr1_filing_period"] for line in lines}
    blocked = {e["period"] for e in truth["itc_at_risk"]
               if e["reason"] == "absent_from_gstr2b"}
    assert len(lines) == len(fee_periods) - len(blocked)
    assert not (blocked & {line["gstr1_filing_period"] for line in lines})


def test_the_monthly_invoice_is_dated_after_the_period_it_covers(gstr2b, truth):
    for line in _razorpay_lines(gstr2b, truth):
        assert line["invoice_date"].endswith("-01")
        assert line["invoice_date"][:7] > line["gstr1_filing_period"]


def test_monthly_invoice_ties_back_to_the_recon_fee_columns(gstr2b, rows, truth):
    """The merchant's ITC claim must reconcile to the fee it actually paid.

    Not to the paise: a real invoice computes GST once on the aggregate, while
    the ledger accrues ceiling-rounded tax per transaction. That difference is
    a genuine reconciliation residual, recorded in the ground-truth key.
    """
    accrued = {}
    for row in rows:
        if row["type"] != "payment" or not row["settled_at"] or not row["tax"]:
            continue
        from datetime import datetime, timedelta, timezone
        ist = timezone(timedelta(hours=5, minutes=30))
        month = datetime.fromtimestamp(row["settled_at"], ist).strftime("%Y-%m")
        acc = accrued.setdefault(month, [0, 0])
        acc[0] += row["fee"] - row["tax"]
        acc[1] += row["tax"]

    residual = {r["period"]: r["residual_paise"]
                for r in truth["gst_rounding_residuals"]}
    checked = 0
    for line in _razorpay_lines(gstr2b, truth):
        period = line["gstr1_filing_period"]
        taxable = _paise(line["taxable_value"])
        tax = _paise(line["cgst"]) + _paise(line["sgst"]) + _paise(line["igst"])
        assert taxable == accrued[period][0], period
        assert tax - accrued[period][1] == residual.get(period, 0), period
        assert abs(tax - accrued[period][1]) < 10000, "residual is not a rounding gap"
        checked += 1
    assert checked >= 2


def test_the_invoiced_tax_is_exactly_eighteen_percent_of_taxable_value(gstr2b, truth):
    """A real consolidated invoice computes GST once on the aggregate, so the
    two halves are equal and the total ties to the rate."""
    for line in _razorpay_lines(gstr2b, truth):
        taxable = _paise(line["taxable_value"])
        cgst, sgst = _paise(line["cgst"]), _paise(line["sgst"])
        assert cgst == sgst, line["invoice_no"]
        assert cgst * 100 - taxable * 9 in range(0, 100), line["invoice_no"]


def test_intra_state_supply_splits_cgst_sgst_and_never_charges_igst(gstr2b, truth):
    """Merchant and Razorpay both registered in Karnataka (state code 29), so
    place of supply under Sec 12(2)(a) IGST Act is intra-state. A merchant in
    another state would receive IGST instead -- that is a property of the
    merchant we chose to model, not a rule."""
    for line in _razorpay_lines(gstr2b, truth):
        assert _paise(line["igst"]) == 0
        assert _paise(line["cgst"]) > 0 and _paise(line["sgst"]) > 0
    assert truth["merchant_gstin"][:2] == truth["razorpay_gstin"][:2] == "29"


def test_every_2b_line_is_either_igst_or_cgst_sgst_never_both(gstr2b):
    for line in gstr2b:
        igst, cgst, sgst = (_paise(line[k]) for k in ("igst", "cgst", "sgst"))
        assert not (igst and (cgst or sgst)), line["invoice_no"]
        assert cgst or sgst or igst, line["invoice_no"]


def test_2b_carries_the_columns_the_itc_decision_actually_depends_on(gstr2b):
    required = {"gstin", "invoice_no", "invoice_date", "taxable_value", "igst",
                "cgst", "sgst", "irn", "irn_generated_at", "gstr1_filing_period",
                "supplier_gstr3b_filed", "itc_availability"}
    assert required <= set(gstr2b[0].keys())


def test_itc_at_risk_covers_three_distinct_statutory_grounds(truth):
    reasons = {e["reason"]: e["statute"] for e in truth["itc_at_risk"]}
    assert reasons["absent_from_gstr2b"] == "Sec 16(2)(aa) CGST"
    assert reasons["no_irn_on_notified_supplier_invoice"] == "Rule 48(5) CGST"
    assert reasons["supplier_gstr3b_not_filed_rule_37a"] == "Rule 37A CGST"
    assert all(e["itc_paise"] > 0 for e in truth["itc_at_risk"])


def test_no_invoice_is_both_present_in_2b_and_missing_from_it(gstr2b, truth):
    present = {line["invoice_no"] for line in gstr2b}
    for entry in truth["itc_at_risk"]:
        if entry["reason"] == "absent_from_gstr2b":
            assert entry["invoice_no"] not in present


def test_the_impossible_late_irn_scenario_is_not_modelled(gstr2b):
    """An invoice whose IRN was not registered inside the reporting window has
    NO IRN -- the IRP refuses it -- so it never auto-populates into GSTR-2B.
    A row that is both in 2B and late-IRN cannot occur, and must not exist here.
    """
    from datetime import date
    for line in gstr2b:
        if not line["irn"]:
            continue
        gap = (date.fromisoformat(line["irn_generated_at"])
               - date.fromisoformat(line["invoice_date"])).days
        assert gap <= 30, f"{line['invoice_no']} is an impossible state"


def test_the_missing_irn_case_is_modelled_instead(gstr2b, truth):
    """Rule 48(5): a notified supplier's invoice without a valid IRN is not a
    tax invoice at all, so ITC fails for want of a valid document."""
    no_irn = [line for line in gstr2b if not line["irn"]]
    assert no_irn, "the Rule 48(5) case is missing"
    flagged = {e["invoice_no"] for e in truth["itc_at_risk"]
               if e["reason"] == "no_irn_on_notified_supplier_invoice"}
    for line in no_irn:
        assert line["invoice_no"] in flagged
        assert line["irn_generated_at"] == ""
        assert line["itc_availability"] == "No"


def test_rule_37a_exposure_is_invisible_in_the_2b_availability_column(gstr2b, truth):
    """GSTR-2B does NOT flag a supplier's unfiled GSTR-3B. That is a condition
    a recon engine has to compute, which is why it is the interesting case."""
    unfiled = [line for line in gstr2b if line["supplier_gstr3b_filed"] == "N"]
    assert unfiled, "the Rule 37A case is missing"
    flagged = {e["invoice_no"] for e in truth["itc_at_risk"]
               if e["reason"] == "supplier_gstr3b_not_filed_rule_37a"}
    for line in unfiled:
        assert line["itc_availability"] == "Yes", \
            "2B would show this as available -- that is the whole point"
        assert line["invoice_no"] in flagged


def test_no_csv_money_column_is_a_bare_float(bank, erp, gstr2b):
    for table, fields in ((bank, ["amount"]), (erp, ["amount"]),
                          (gstr2b, ["taxable_value", "igst", "cgst", "sgst"])):
        for line in table:
            for field in fields:
                assert MONEY.match(line[field]), (field, line[field])
