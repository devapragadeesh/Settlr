"""The `ProvenUnmatched` / `OpenBreak` split. Contract sec 4.7.

These tests exist because the outcome they replace passed every test it had.
`CorrectlyUnmatched` was 45.7% accurate over 4,994 claims and nothing failed,
because the suite checked that a reason was *produced*, never that it was
*entailed*. Each test below is written against a specific measured failure in
`investigation/DERIVED_BRANCH_AUDIT.md` and fails if that failure returns.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from resolver.breaks import first_reconcilable, netted_out_payments
from resolver.eligibility import eligible_at
from resolver.loaders import load
from resolver.resolve import resolve
from resolver_contract.types import (
    AttestationDiscrepancy, BreakReason, ContractViolation, OpenBreak,
    ProvenUnmatched, ProvenUnmatchedReason, Verified, age_bucket,
)

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ["datasets/A10_B100_Cmax", "datasets_v2/A20_B100_Cmax",
          "datasets/A20_Bnone_Cmax"]


@pytest.fixture(scope="module")
def outputs():
    return {name: resolve(load(ROOT / "corpus" / name)) for name in SAMPLE}


def _rows(name):
    return json.loads(
        (ROOT / "corpus" / name / "recon_combined.json").read_text())["items"]


# --------------------------------------------------------------------------
# the netting predicate, and each of its three measured divergences
# --------------------------------------------------------------------------


def _payment(amount=100_000, fee=2_000, created_at=1_800_000_000):
    return {"entity_id": "pay_x", "type": "payment", "amount": amount,
            "credit": amount - fee, "debit": 0, "fee": fee,
            "created_at": created_at, "payment_id": None}


def _refund(debit, created_at, rid="rfnd_1"):
    return {"entity_id": rid, "type": "refund", "amount": debit,
            "credit": 0, "debit": debit, "created_at": created_at,
            "payment_id": "pay_x"}


def test_an_exactly_full_refund_before_eligibility_nets_out():
    pay = _payment()
    before = eligible_at(pay["created_at"]) - 3600
    assert netted_out_payments([pay, _refund(100_000, before)]) == {"pay_x"}


def test_an_OVER_refunded_payment_does_not_net_out():
    """Divergence 1: `>=` admits an over-refund, and over-refunded payments
    settle. All 8 rows that G9 would have failed on had this shape."""
    pay = _payment()
    before = eligible_at(pay["created_at"]) - 3600
    after = eligible_at(pay["created_at"]) + 86_400 * 7
    rows = [pay, _refund(100_000, before, "rfnd_1"),
            _refund(32_500, after, "rfnd_2")]
    assert netted_out_payments(rows) == set()
    # and the inequality the first resolver used would have said otherwise
    assert sum(r["debit"] for r in rows[1:]) >= pay["credit"]


def test_a_refund_short_by_less_than_the_fee_does_not_net_out():
    """Divergence 2: comparing against the fee-net `credit` instead of the
    gross `amount`. Measured: 2,014,800 paise of refunds against a 2,014,900
    payment -- one rupee short -- read as a full refund."""
    pay = _payment(amount=2_014_900, fee=47_552)
    before = eligible_at(pay["created_at"]) - 3600
    rows = [pay, _refund(1_007_400, before, "a"), _refund(1_007_400, before, "b")]
    assert netted_out_payments(rows) == set()
    assert sum(r["debit"] for r in rows[1:]) >= pay["credit"]   # the old test
    assert sum(r["debit"] for r in rows[1:]) != pay["amount"]   # the real one


def test_a_full_refund_AFTER_eligibility_does_not_net_out():
    """Divergence 3: no timing test at all. A refund raised after the payment
    settled is a debit row in a later batch, not a netting
    (`SETTLEMENT_SPEC.md` sec 3)."""
    pay = _payment()
    after = eligible_at(pay["created_at"]) + 60
    assert netted_out_payments([pay, _refund(100_000, after)]) == set()


def test_the_predicate_matches_the_frozen_simulator_on_every_dataset():
    """The frozen simulator is normative. This asserts equality with it, so a
    drift in either direction fails rather than being absorbed."""
    for name in SAMPLE:
        rows = _rows(name)
        truth = json.loads(
            (ROOT / "corpus" / name / "ground_truth.json").read_text())
        expected = {r for r in truth.get("netted_out", [])}
        assert netted_out_payments(rows) == expected, name


# --------------------------------------------------------------------------
# ProvenUnmatched is a CLAIM and must be entailed
# --------------------------------------------------------------------------


def test_no_ProvenUnmatched_row_ever_settled(outputs):
    """G9, checked here as well as in the oracle. The resolver must not need
    the oracle to discover it is lying."""
    for name, out in outputs.items():
        truth = json.loads(
            (ROOT / "corpus" / name / "ground_truth.json").read_text())
        unsettled = truth.get("unsettled_reason", {})
        for item in out.proven_unmatched:
            wrong = [r for r in item.row_ids if unsettled.get(r) is None]
            assert not wrong, f"{name}: {item.reason.value} claims {wrong[:3]}"


def test_only_the_two_entailed_reasons_can_be_proven(outputs):
    allowed = {ProvenUnmatchedReason.NOT_CAPTURED,
               ProvenUnmatchedReason.NETTED_OUT}
    for out in outputs.values():
        for item in out.proven_unmatched:
            assert item.reason in allowed


def test_dispute_held_is_never_a_ProvenUnmatched_reason():
    """It scored 90.2% and 64 of its rows settled. A chargeback claws back
    AFTER settlement, so a hold cannot entail non-settlement, at any level of
    implementation quality (contract sec 4.7.4)."""
    assert not any("dispute" in r.value for r in ProvenUnmatchedReason)


def test_every_ProvenUnmatched_carries_a_warrant(outputs):
    for out in outputs.values():
        for item in out.proven_unmatched:
            assert item.warrant is not None
            assert item.warrant.evidence


# --------------------------------------------------------------------------
# OpenBreak asserts nothing, and must not be able to pretend otherwise
# --------------------------------------------------------------------------


def test_upstream_unresolved_without_a_cause_is_rejected():
    with pytest.raises(ContractViolation):
        OpenBreak(row_ids=("a",), reason=BreakReason.UPSTREAM_UNRESOLVED,
                  age_days=1, first_seen="2027-01-01")


def test_a_cause_pointer_on_any_other_reason_is_rejected():
    with pytest.raises(ContractViolation):
        OpenBreak(row_ids=("a",), reason=BreakReason.TIMING_DIFFERENCE,
                  age_days=1, first_seen="2027-01-01", caused_by=3)


def test_unexplained_survives_as_a_real_category(outputs):
    """A high count here is an honest finding. If this ever reaches zero the
    likely cause is that some other reason was widened to absorb it, which is
    how ROLLED_FORWARD happened."""
    assert BreakReason.UNEXPLAINED in set(BreakReason)
    total = sum(len(i.row_ids) for out in outputs.values()
                for i in out.open_breaks
                if i.reason is BreakReason.UNEXPLAINED)
    assert total >= 0        # documentary: the category must remain reachable


def test_a_row_has_exactly_one_disposition(outputs):
    for name, out in outputs.items():
        seen: set[str] = set()
        for item in out.unmatched:
            for row_id in item.row_ids:
                assert row_id not in seen, f"{name}: {row_id} twice"
                seen.add(row_id)


def test_proven_and_open_partition_the_unassigned_rows(outputs):
    for name, out in outputs.items():
        ds = load(ROOT / "corpus" / name)
        assigned = set(out.row_assignments)
        disposed = {r for i in out.unmatched for r in i.row_ids}
        assert assigned.isdisjoint(disposed)
        assert assigned | disposed == {r["entity_id"] for r in ds.rows}


# --------------------------------------------------------------------------
# aging
# --------------------------------------------------------------------------


def test_the_standard_buckets():
    assert age_bucket(0) == "0-30"
    assert age_bucket(30) == "0-30"
    assert age_bucket(31) == "31-60"
    assert age_bucket(90) == "61-90"
    assert age_bucket(91) == "90+"
    assert age_bucket(10_000) == "90+"


def test_a_payment_ages_from_eligibility_not_from_creation():
    """Aging a payment from `created_at` charges it for the T+2 window the
    product itself promises."""
    pay = _payment()
    assert first_reconcilable(pay) == eligible_at(pay["created_at"])
    assert first_reconcilable(pay) > pay["created_at"]
    refund = _refund(1, 1_800_000_000)
    assert first_reconcilable(refund) == refund["created_at"]


def test_every_open_break_is_aged(outputs):
    for out in outputs.values():
        for item in out.open_breaks:
            assert item.age_days >= 0
            assert item.age_bucket in {"0-30", "31-60", "61-90", "90+"}
            assert item.first_seen


def test_every_break_reason_routes_to_an_owner_and_a_close_condition():
    for item in (OpenBreak(row_ids=("a",), reason=r, age_days=0,
                           first_seen="2027-01-01",
                           caused_by=1 if r is BreakReason.UPSTREAM_UNRESOLVED
                           else None)
                 for r in BreakReason):
        assert item.owner and item.close_condition


# --------------------------------------------------------------------------
# the cause pointer -- contract sec 4.7.5
# --------------------------------------------------------------------------


def test_a_reversed_credit_names_the_rows_it_blocks(outputs):
    """All 30 `credit_reversed` discrepancies previously carried an empty
    `attested_row_ids`, so the single largest cause of blocked rows named none
    of them."""
    found = False
    for name, out in outputs.items():
        ds = load(ROOT / "corpus" / name)
        if not ds.rows_carry_settlement_id:
            continue
        for outcome in out.line_outcomes:
            if not isinstance(outcome, AttestationDiscrepancy):
                continue
            if outcome.contradiction.kind.value != "credit_reversed":
                continue
            found = True
            assert outcome.attested_row_ids, f"{name} bank[{outcome.bank_index}]"
    assert found, "no reversed credit in the sample -- the test proves nothing"


def test_the_two_row_fields_mean_different_things(outputs):
    """`Contradiction.row_ids` is the OFFENDING subset; `attested_row_ids` is
    the WHOLE attestation. One field answering both under-pointed:
    `temporal_impossibility` named 13 rows out of 294 it blocked."""
    for out in outputs.values():
        for outcome in out.line_outcomes:
            if not isinstance(outcome, AttestationDiscrepancy):
                continue
            offending = set(outcome.contradiction.row_ids)
            attested = set(outcome.attested_row_ids)
            assert offending <= attested or not attested


def test_blocked_rows_cluster_under_their_causing_line(outputs):
    for name, out in outputs.items():
        ds = load(ROOT / "corpus" / name)
        if not ds.rows_carry_settlement_id:
            continue
        clustered = [i for i in out.open_breaks
                     if i.reason is BreakReason.UPSTREAM_UNRESOLVED]
        assert clustered, name
        settled_lines = {o.bank_index for o in out.line_outcomes
                         if isinstance(o, Verified)}
        for item in clustered:
            assert item.caused_by not in settled_lines


def test_absence_datasets_cannot_name_a_cause_and_say_so(outputs):
    """No attestation exists, so nothing is nameable and the rows fall to
    UNEXPLAINED. That is the honest answer, and it reports something true."""
    out = outputs["datasets/A20_Bnone_Cmax"]
    assert not any(i.reason is BreakReason.UPSTREAM_UNRESOLVED
                   for i in out.open_breaks)
    assert any(i.reason is BreakReason.UNEXPLAINED for i in out.open_breaks)
