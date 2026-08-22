"""All 15 planted classes present, counts within tolerance. Task 2."""

from collections import Counter

import pytest

#: class -> (minimum, maximum). Deliberately wide: the generator plants ROLES
#: and the labels are derived from what the simulator ACTUALLY did, so exact
#: counts are an emergent property, not a dial.
TARGETS = {
    "c01_clean_1to1": (140, 175),
    "c02_full_refund_pre_settlement": (5, 20),
    "c03_partial_refund_pre_settlement": (8, 30),
    "c04_refund_in_later_batch": (6, 25),
    "c05_subset_sum_rolled_forward": (5, 25),
    "c06_netting": (6, 12),
    "c07_ambiguous_decomposition": (1, 4),
    "c08_dispute_hold": (3, 8),
    "c09_lost_dispute_adjustment": (3, 8),
    "c10_won_dispute_settles_later": (2, 8),
    "c11_cross_month_boundary": (8, 60),
    "c12_shared_sid_null_utr": (4, 25),
    "c13_schema_variance": (20, 80),
    "c14_corrupt_bank_narration": (2, 5),
    # Not in the original 14. Added after independent audit: a matcher keying
    # on (amount, date) alone must not be able to separate these.
    "c15_same_day_same_amount_decoy": (4, 10),
}


def counts(truth):
    tally = Counter()
    for classes in truth["row_classes"].values():
        tally.update(classes)
    for batch in truth["batches"]:
        tally.update(batch["classes"])
    return tally


def test_all_fifteen_classes_are_present(truth):
    tally = counts(truth)
    missing = sorted(set(TARGETS) - set(tally))
    assert not missing, f"classes absent from the dataset: {missing}"


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_class_count_is_within_tolerance(truth, name):
    low, high = TARGETS[name]
    actual = counts(truth)[name]
    assert low <= actual <= high, f"{name}: {actual} outside [{low}, {high}]"


def test_no_unexpected_class_labels(truth):
    assert not set(counts(truth)) - set(TARGETS)


def test_hard_cases_are_a_meaningful_share_of_the_dataset(truth, rows):
    hard = {"c02_full_refund_pre_settlement", "c03_partial_refund_pre_settlement",
            "c04_refund_in_later_batch", "c05_subset_sum_rolled_forward",
            "c08_dispute_hold", "c09_lost_dispute_adjustment",
            "c10_won_dispute_settles_later"}
    flagged = {e for e, classes in truth["row_classes"].items()
               if hard & set(classes)}
    share = len(flagged) * 100 // len(rows)
    assert 12 <= share <= 30, f"hard-case share is {share}%"


def test_clean_rows_dominate_as_they_do_in_production(truth, rows):
    clean = sum(1 for classes in truth["row_classes"].values()
                if "c01_clean_1to1" in classes)
    assert clean * 100 // len(rows) >= 55


def test_source_tier_distribution_covers_all_three_tiers(rows):
    tally = Counter(r["source_tier"] for r in rows)
    assert set(tally) == {"captured_real", "synthesized_documented",
                          "synthesized_modelled"}
    assert all(count > 5 for count in tally.values())


def test_source_tier_is_not_a_shortcut_to_hard_cases(truth, rows):
    """If every hard case were one tier, a solver could cheat on provenance."""
    hard = {e for e, classes in truth["row_classes"].items()
            if any(c not in ("c01_clean_1to1", "c11_cross_month_boundary",
                             "c13_schema_variance") for c in classes)}
    tiers = Counter(r["source_tier"] for r in rows if r["entity_id"] in hard)
    assert len(tiers) >= 2, "hard cases sit in a single provenance tier"
    clean_tiers = Counter(r["source_tier"] for r in rows
                          if r["entity_id"] not in hard)
    assert set(tiers) & set(clean_tiers), "tiers perfectly separate hard from clean"


def test_method_mix_is_realistic(rows):
    """UPI-dominant by count, as an Indian merchant book is. The captured
    account produced netbanking and wallet only, so the mix is modelled."""
    methods = Counter(r["method"] for r in rows if r["type"] == "payment")
    assert set(methods) == {"netbanking", "card", "wallet", "upi"}
    assert methods["upi"] > methods["netbanking"] > methods["wallet"]
    assert methods["card"] > 20, "too few card rows to exercise card metadata"


def test_every_card_network_and_mdr_tier_appears(rows):
    networks = Counter((r["card_network"], r["card_type"])
                       for r in rows if r["method"] == "card")
    assert {"Visa", "MasterCard", "RuPay", "Amex"} <= {n for n, _t in networks}
    assert ("RuPay", "debit") in networks, "the zero-MDR card case is missing"
    assert any(n == "Amex" for n, _t in networks), "the 3% MDR case is missing"


def test_decoy_pairs_are_genuinely_indistinguishable_on_amount_and_date(rows, truth):
    from datetime import datetime, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    by_id = {r["entity_id"]: r for r in rows}
    assert truth["decoy_pairs"], "no decoys planted"
    for source_id, target_id in truth["decoy_pairs"]:
        a, b = by_id[source_id], by_id[target_id]
        assert a["amount"] == b["amount"]
        assert (datetime.fromtimestamp(a["created_at"], ist).date()
                == datetime.fromtimestamp(b["created_at"], ist).date())
        assert a["entity_id"] != b["entity_id"]
        assert a["order_id"] != b["order_id"]


def test_every_declared_plant_either_succeeded_or_says_it_did_not(truth):
    """A generator that can silently under-deliver its hardest class is a
    generator whose output means nothing."""
    import generator
    assert len(truth["planted_ambiguity"]) == len(generator.AMBIGUITY_BATCHES)
    assert len(truth["planted_balance_pressure"]) == len(generator.PRESSURE_BATCHES)
    for entry in truth["planted_ambiguity"]:
        assert "planted" in entry
        if entry["planted"]:
            assert entry["settlement_id"]
        else:
            assert entry["reason"]
    for entry in truth["planted_balance_pressure"]:
        assert "planted" in entry
    achieved = [e for e in truth["planted_ambiguity"] if e["planted"]]
    assert len(achieved) >= 2, "fewer ambiguities planted than declared"


def test_a_missed_plant_is_recorded_rather_than_vanishing(truth):
    """The guard must be exercised, not merely present. If every plant lands,
    this test is a no-op; if one does not, it must appear in the key with a
    reason rather than silently reducing the class count."""
    for key in ("planted_ambiguity", "planted_balance_pressure"):
        for entry in truth[key]:
            if not entry["planted"]:
                assert entry["reason"], entry
                # the id may still name the batch that RESISTED planting --
                # what must not happen is the attempt vanishing from the record
                assert "excluded_credit" not in entry


def test_planting_records_point_at_settlement_ids_that_exist(truth):
    real = {b["settlement_id"] for b in truth["batches"]}
    for key in ("planted_ambiguity", "planted_balance_pressure"):
        for entry in truth[key]:
            if entry.get("settlement_id"):
                assert entry["settlement_id"] in real, (key, entry)


def test_at_least_two_batches_require_a_multi_payment_exclusion(truth):
    """"Drop exactly one" is a linear scan, not subset-sum. The hard cases
    must be harder than the easiest instance of their own class."""
    import generator
    deep = [e for e in truth["planted_balance_pressure"]
            if e["batch_index"] in generator.DEEP_PRESSURE_BATCHES and e["planted"]]
    assert len(deep) >= 2
    single = max(b["credit_total"] for b in truth["batches"]) // len(truth["batches"])
    assert all(e["excluded_credit"] > single for e in deep), \
        "the deep-pressure batches drop no more than one average payment"


def test_disputes_cover_every_modelled_outcome(disputes):
    statuses = Counter(d["status"] for d in disputes)
    assert {"under_review", "won", "lost"} <= set(statuses)
