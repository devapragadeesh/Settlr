"""Batch 11 -- the negative live balance, asserted by name.

Spec sec 1.4: when a batch's debits exceed what it can pay out, debits are
deferred. `setl_rrj3aCVGDyESrb` has a computed live balance of -160,835 paise
and settles a credit adjustment with FIVE debits deferred.

This is real adversarial data, not a hypothetical. It must fall out of the
general solver -- nothing in `matching/` names this batch, and these tests
assert that the general machinery produced the right answer rather than a
special case that only works because someone knew it was there.
"""

import pytest

from matching.model import Ambiguous, Determinate

SETTLEMENT_ID = "setl_rrj3aCVGDyESrb"


@pytest.fixture(scope="module")
def batch11(cascade):
    index = next(i for i, sid in cascade.bank_to_batch.items() if sid == SETTLEMENT_ID)
    reconstruction = cascade.stage3.by_bank_index(index)
    assert reconstruction is not None
    return reconstruction


def test_the_batch_exists_and_is_reached_by_the_cascade(cascade):
    assert SETTLEMENT_ID in cascade.bank_to_batch.values()


def test_its_bank_line_has_no_utr_hint_and_is_recovered_by_stage2(cascade, batch11):
    """Its only ledger row is an adjustment, and adjustments carry a null
    settlement_utr -- so there is no join key on the LEDGER side. A different
    failure from the blank-utr line, recovered by the same fallback."""
    assert batch11.bank_index in cascade.stage2.bank_to_batch
    note = cascade.stage2.recovery_notes[batch11.bank_index]
    assert "settlement_utr null" in note


def test_it_resolves_determinately_despite_the_negative_balance(batch11):
    assert isinstance(batch11.resolution, Determinate)
    assert batch11.resolution.proof.holds
    assert batch11.resolution.proof.residual == 0


def test_debits_were_deferred_rather_than_forced_into_the_batch(batch11):
    """The min-deferral objective permits deferral exactly when arithmetic
    forces it. Here it forces five."""
    assert batch11.deferred_debits == 5


def test_the_batch_settles_a_credit_adjustment_and_no_payments(batch11, dataset):
    rows = {row["entity_id"]: row for row in dataset.rows}
    placed = batch11.resolution.decomposition.row_ids
    assert placed, "nothing placed"
    assert all(rows[row_id]["type"] == "adjustment" for row_id in placed)
    assert not any(rows[row_id]["type"] == "payment" for row_id in placed)


def test_the_true_live_balance_was_negative(truth):
    batch = next(b for b in truth["batches"] if b["settlement_id"] == SETTLEMENT_ID)
    assert batch["available_live_balance"] < 0
    assert batch["selected_payment_credit"] == 0
    assert batch["bank_payout"] > 0


def test_the_deferred_debits_are_reported_not_silently_dropped(cascade, truth):
    """Nothing vanishes. Every deferred debit reaches the exception queue."""
    deferred_truth = {row_id for row_id, reason in truth["unsettled_reason"].items()
                      if reason == "debit_deferred_past_horizon"}
    unplaced = deferred_truth - set(cascade.stage3.assigned)
    reported = {item.entity_id for item in cascade.stage4.exceptions}
    assert unplaced <= reported


def test_no_module_hardcodes_this_batch(cascade):
    """The general logic must produce this, not a branch that knows the answer."""
    from pathlib import Path
    matching = Path(__file__).resolve().parent.parent / "matching"
    for path in matching.rglob("*.py"):
        assert SETTLEMENT_ID not in path.read_text(), path.name
        assert "160835" not in path.read_text(), path.name
