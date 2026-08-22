"""Schema conformance and the verified quirk list. SETTLEMENT_SPEC.md sec 5."""

import json

RECON_FIELDS = [
    "entity_id", "type", "debit", "credit", "amount", "currency", "fee", "tax",
    "on_hold", "settled", "created_at", "settled_at", "settlement_id",
    "posted_at", "credit_type", "description", "notes", "payment_id",
    "settlement_utr", "order_id", "order_receipt", "method", "card_network",
    "card_issuer", "card_type", "dispute_id",
]
PROVENANCE_FIELDS = ["source_tier", "source_ref"]
MONEY_FIELDS = ["debit", "credit", "amount", "fee", "tax"]
TIERS = {"captured_real", "synthesized_documented", "synthesized_modelled"}


def test_shape(recon):
    assert recon["entity"] == "collection"
    assert recon["count"] == len(recon["items"]) == 240


def test_every_documented_field_is_present_or_deliberately_absent(rows):
    for row in rows:
        expected = list(RECON_FIELDS)
        if row["type"] == "adjustment":
            # `credit_type` is ABSENT on adjustment rows -- not null.
            expected.remove("credit_type")
        assert list(row.keys()) == expected + PROVENANCE_FIELDS, row["entity_id"]


def test_credit_type_is_absent_only_on_adjustments(rows):
    for row in rows:
        if row["type"] == "adjustment":
            assert "credit_type" not in row
        else:
            assert row["credit_type"] == "default"


def test_notes_is_object_or_array_never_null_never_a_string(rows):
    for row in rows:
        assert isinstance(row["notes"], (dict, list)), row["entity_id"]
        assert row["notes"] is not None
        assert not isinstance(row["notes"], str)


def test_entity_id_payment_id_resolution_rule_holds_on_every_row(rows):
    """`entity_id if type == 'payment' else payment_id`."""
    payment_ids = {r["entity_id"] for r in rows if r["type"] == "payment"}
    for row in rows:
        if row["type"] == "payment":
            assert row["payment_id"] is None, row["entity_id"]
            assert row["entity_id"].startswith("pay_")
        elif row["type"] == "refund":
            assert row["payment_id"] in payment_ids
            assert row["entity_id"].startswith("rfnd_")
        elif row["type"] == "adjustment":
            # unjoinable by construction -- must route to the exception queue
            assert row["payment_id"] is None
            assert row["order_id"] is None
            assert row["method"] is None
            assert row["entity_id"].startswith("adj_")
        resolved = row["entity_id"] if row["type"] == "payment" else row["payment_id"]
        assert resolved is None or isinstance(resolved, str)


def test_settlement_utr_is_null_on_adjustments_that_carry_a_settlement_id(rows):
    """UTR is NOT a batch-level key -- join on settlement_id."""
    shared = [r for r in rows if r["type"] == "adjustment" and r["settlement_id"]]
    assert shared, "no adjustment shares a settlement_id -- class 12 is missing"
    for row in shared:
        assert row["settlement_utr"] is None

    by_sid = {}
    for row in rows:
        if row["settlement_id"] and row["settlement_utr"]:
            by_sid.setdefault(row["settlement_id"], set()).add(row["settlement_utr"])
    for sid, utrs in by_sid.items():
        assert len(utrs) == 1, sid


def test_no_float_anywhere_in_monetary_fields(rows):
    raw = json.dumps(rows)
    for row in rows:
        for field in MONEY_FIELDS:
            value = row[field]
            assert value is None or isinstance(value, int), (row["entity_id"], field)
            assert not isinstance(value, bool)
    assert "." not in "".join(
        str(row[f]) for row in rows for f in MONEY_FIELDS if row[f] is not None)
    assert "e-" not in raw.lower().split('"source_ref"')[0]


def test_failed_payments_carry_null_fee_and_never_settle(rows):
    failed = [r for r in rows
              if r["type"] == "payment" and r["fee"] is None]
    assert failed, "no uncaptured payments -- the fee=null case is missing"
    for row in failed:
        assert row["tax"] is None
        assert row["credit"] == 0
        assert row["settled"] is False
        assert row["settlement_id"] is None


def test_settled_rows_carry_a_batch_and_unsettled_rows_do_not(rows):
    for row in rows:
        if row["settled"]:
            assert row["settlement_id"] and row["settled_at"]
            assert row["settled_at"] >= row["created_at"], row["entity_id"]
        else:
            assert row["settlement_id"] is None
            assert row["settled_at"] is None
            assert row["settlement_utr"] is None


def test_source_tier_is_present_and_valid_on_every_row(rows):
    for row in rows:
        assert row["source_tier"] in TIERS, row["entity_id"]
        assert row["source_ref"], row["entity_id"]


def test_captured_real_rows_mirror_an_actual_captured_payment(rows, captured):
    by_id = {p["id"]: p for p in captured["payments"]}
    real = [r for r in rows if r["source_tier"] == "captured_real"]
    assert real, "nothing is tiered captured_real"
    for row in real:
        origin = row["source_ref"].split("::")[1]
        source = by_id[origin]
        assert row["amount"] == source["amount"]
        assert row["fee"] == source["fee"]
        assert row["tax"] == source["tax"]
        assert row["method"] == source["method"]


def test_card_and_upi_rows_never_claim_to_be_captured(rows):
    """Card was WAF-blocked and UPI was disabled on the captured account."""
    for row in rows:
        if row["method"] in ("card", "upi"):
            assert row["source_tier"] == "synthesized_modelled", row["entity_id"]


def test_card_fields_populate_only_on_card_rows(rows):
    for row in rows:
        card_fields = (row["card_network"], row["card_issuer"], row["card_type"])
        if row["method"] == "card":
            assert all(card_fields), row["entity_id"]
        else:
            assert not any(card_fields), row["entity_id"]


def test_dispute_rows_are_internally_consistent(rows, disputes):
    by_payment = {d["payment_id"]: d for d in disputes}
    for row in rows:
        if row["type"] != "payment" or not row["dispute_id"]:
            continue
        dispute = by_payment[row["entity_id"]]
        assert dispute["id"] == row["dispute_id"]
        assert dispute["created_at"] >= row["created_at"]
        # amount_deducted is 0 unless the dispute was lost
        assert (dispute["amount_deducted"] != 0) == (dispute["status"] == "lost")
        if row["on_hold"]:
            assert row["settled"] is False


def test_rows_are_ordered_and_ids_are_unique(rows):
    assert len({r["entity_id"] for r in rows}) == len(rows)
    keys = [(r["created_at"], r["entity_id"]) for r in rows]
    assert keys == sorted(keys)
