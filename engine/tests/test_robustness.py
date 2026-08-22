"""The planted classes must survive seeds nobody chose.

This is the real answer to "you tuned the data until it worked": the property
must hold for seeds selected before any of them was inspected.

Slower than the rest of the suite. Run the full 20-seed sweep with
`python3 engine/robustness.py`.
"""

import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

import generator  # noqa: E402

#: chosen as "the first five integers", not by inspection
SEEDS = [0, 1, 2, 3, 4]
#: the sweep is the slowest thing in the suite; the full 20-seed table lives
#: in ROBUSTNESS.md and is produced by `python3 engine/robustness.py`

#: classes that must appear for EVERY seed, not just the shipped one
ALWAYS = [
    "c01_clean_1to1", "c02_full_refund_pre_settlement",
    "c03_partial_refund_pre_settlement", "c04_refund_in_later_batch",
    "c05_subset_sum_rolled_forward", "c06_netting", "c08_dispute_hold",
    "c09_lost_dispute_adjustment", "c11_cross_month_boundary",
    "c12_shared_sid_null_utr", "c13_schema_variance",
    "c14_corrupt_bank_narration", "c15_same_day_same_amount_decoy",
]


@pytest.fixture(scope="module")
def sweep():
    out = []
    for seed in SEEDS:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows, result, labels, batch_labels, counts = generator.generate(
                seed, tmp / "d", tmp / "t")
        out.append((seed, rows, result, counts))
    return out


@pytest.mark.parametrize("name", ALWAYS)
def test_class_survives_every_unchosen_seed(sweep, name):
    missing = [seed for seed, _rows, _res, counts in sweep if not counts.get(name)]
    assert not missing, f"{name} absent for seeds {missing}"


def test_the_generator_never_crashes_on_an_unchosen_seed(sweep):
    assert len(sweep) == len(SEEDS)


def test_shape_is_stable_across_seeds(sweep):
    """A batch can legitimately fail to form -- nothing eligible, or no
    non-negative payout reachable (SETTLEMENT_SPEC.md sec 1.4). What must not
    vary is the order of magnitude."""
    for seed, rows, result, _counts in sweep:
        assert 225 <= len(rows) <= 260, (seed, len(rows))
        assert 10 <= len(result.batches) <= 12, (seed, len(result.batches))


def test_the_pool_ceiling_degrades_rather_than_raising(sweep):
    """Above `max_pool` exact enumeration is the wrong algorithm. The batch
    must fall back to the FIFO reading and SAY SO, not raise."""
    for seed, _rows, result, _counts in sweep:
        for batch in result.batches:
            if batch.pool_size > 28:
                assert batch.selection_degraded, (seed, batch.settlement_id)
            else:
                assert not batch.selection_degraded, (seed, batch.settlement_id)


def test_a_degraded_batch_is_never_reported_as_ambiguous(sweep):
    """The FIFO reading has no tie-break, so it cannot discover ambiguity.
    Claiming a degraded batch is unambiguous would be an unearned assertion."""
    for seed, _rows, result, _counts in sweep:
        for batch in result.batches:
            if batch.selection_degraded:
                assert len(batch.tying_decompositions) == 1, (seed, batch.settlement_id)


def test_accounting_closes_for_every_seed(sweep):
    for seed, rows, result, _counts in sweep:
        for batch in result.batches:
            credit = sum(r["credit"] for r in rows
                         if r["settlement_id"] == batch.settlement_id)
            debit = sum(r["debit"] for r in rows
                        if r["settlement_id"] == batch.settlement_id)
            assert credit - debit == batch.payout, (seed, batch.settlement_id)
            assert batch.payout >= 0, (seed, batch.settlement_id)


def test_the_fee_identity_holds_for_every_seed(sweep):
    for seed, rows, _res, _counts in sweep:
        for row in rows:
            if row["type"] == "payment" and row["fee"] is not None:
                assert row["credit"] == row["amount"] - row["fee"], (seed, row["entity_id"])


def test_ambiguity_is_reachable_across_seeds(sweep):
    """Not every seed must produce one -- but the class must not be an
    artefact of the single shipped seed."""
    with_ambiguity = [seed for seed, _r, result, _c in sweep
                      if any(b.ambiguous for b in result.batches)]
    assert len(with_ambiguity) >= len(SEEDS) - 1, \
        f"ambiguity only reachable on seeds {with_ambiguity}"


def test_all_three_provenance_tiers_appear_for_every_seed(sweep):
    for seed, rows, _res, _counts in sweep:
        tiers = Counter(r["source_tier"] for r in rows)
        assert set(tiers) == {"captured_real", "synthesized_documented",
                              "synthesized_modelled"}, seed
