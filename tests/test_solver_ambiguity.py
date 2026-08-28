"""The ambiguity contract, asserted against ACTUAL solver output.

`engine/tests/test_ambiguity.py` encoded this contract before any solver
existed. These tests run it against what the solver really returns.
"""

import random

import pytest

import matching.stage3_solver as stage3_solver
from matching.model import (
    Ambiguous, BalanceProof, BalanceViolation, Decomposition, Determinate,
    Unresolved, resolve_from_candidates,
)
from matching.stage3_solver import enumerate_decompositions


def ambiguous_reconstructions(cascade):
    return [item for item in cascade.stage3.reconstructions
            if isinstance(item.resolution, Ambiguous)]


# --- the structural guarantee ---------------------------------------------

def test_an_ambiguous_result_has_no_decomposition_attribute(cascade):
    """The contract is structural. There is no field to read and no flag to
    forget: a confident single answer is UNREPRESENTABLE, not discouraged."""
    found = ambiguous_reconstructions(cascade)
    assert found, "no ambiguous batch in solver output -- contract untested"
    for item in found:
        assert not hasattr(item.resolution, "decomposition")
        assert not hasattr(item.resolution, "assignment")
        with pytest.raises(AttributeError):
            _ = item.resolution.decomposition


def test_a_determinate_result_cannot_be_built_from_two_candidates():
    a = Decomposition(("x",), (), 100, 0)
    b = Decomposition(("y",), (), 100, 0)
    resolution = resolve_from_candidates(
        [a, b], bank_amount=100, truncated=False, method="test",
        pool_size=2, enumeration_cap=32)
    assert isinstance(resolution, Ambiguous)
    assert not isinstance(resolution, Determinate)


def test_ambiguous_requires_at_least_two_candidates():
    with pytest.raises(ValueError):
        Ambiguous(candidates=(Decomposition(("x",), (), 1, 0),), truncated=False,
                  method="test", enumeration_cap=32)


def test_one_candidate_plus_truncation_is_not_determinate():
    """Truncation means enumeration stopped early, so "one found" is not
    "one exists". Reporting it as determinate would assert something never
    checked."""
    resolution = resolve_from_candidates(
        [Decomposition(("x",), (), 100, 0)], bank_amount=100, truncated=True,
        method="test", pool_size=9, enumeration_cap=1)
    assert isinstance(resolution, Unresolved)
    assert "truncated" in resolution.reason


def test_enumerate_first_then_decide_never_pick_then_check(cascade):
    """Every resolution's confidence follows from the candidate COUNT."""
    for item in cascade.stage3.reconstructions:
        resolution = item.resolution
        if isinstance(resolution, Ambiguous):
            assert len(resolution.candidates) >= 2
            assert resolution.is_confident is False
        elif isinstance(resolution, Determinate):
            assert resolution.is_confident is True


# --- the grading contract -------------------------------------------------

FLAG = "FLAG_AMBIGUOUS"


def verdict(resolution, answer):
    if isinstance(resolution, Ambiguous):
        return "pass" if answer == FLAG else "fail"
    if isinstance(resolution, Determinate):
        return ("pass" if answer != FLAG
                and sorted(answer) == sorted(resolution.decomposition.row_ids)
                else "fail")
    return "pass" if answer == FLAG else "fail"


def test_a_confident_single_answer_on_an_ambiguous_batch_FAILS(cascade):
    """Even naming a candidate the solver itself enumerated must fail: the
    solver could not have known which one is true."""
    found = ambiguous_reconstructions(cascade)
    assert found
    for item in found:
        for candidate in item.resolution.candidates:
            assert verdict(item.resolution, candidate.row_ids) == "fail"


def test_flagging_an_ambiguous_batch_passes(cascade):
    for item in ambiguous_reconstructions(cascade):
        assert verdict(item.resolution, FLAG) == "pass"


def test_flagging_everything_is_not_a_way_to_pass(cascade):
    determinate = [item for item in cascade.stage3.reconstructions
                   if isinstance(item.resolution, Determinate)]
    assert determinate
    for item in determinate:
        assert verdict(item.resolution, FLAG) == "fail"


# --- correctness of the enumeration --------------------------------------

def test_every_candidate_of_an_ambiguous_batch_nets_to_the_bank_amount(cascade):
    for item in ambiguous_reconstructions(cascade):
        for candidate in item.resolution.candidates:
            assert candidate.net == item.bank_amount, item.bank_index


def test_candidates_are_distinct_and_deterministically_ordered(cascade):
    for item in ambiguous_reconstructions(cascade):
        rows = [candidate.row_ids for candidate in item.resolution.candidates]
        assert len(set(rows)) == len(rows)
        assert rows == sorted(rows)


def test_certain_rows_appear_in_every_candidate(cascade):
    for item in ambiguous_reconstructions(cascade):
        resolution = item.resolution
        for row_id in resolution.certain_rows:
            assert all(row_id in c.row_ids for c in resolution.candidates)
        for row_id in resolution.contested_rows:
            assert not all(row_id in c.row_ids for c in resolution.candidates)
            assert any(row_id in c.row_ids for c in resolution.candidates)


def test_certain_rows_are_empty_when_enumeration_truncated():
    """An unseen candidate could drop any of them, so optimism is unfounded."""
    resolution = Ambiguous(
        candidates=(Decomposition(("a", "b"), (), 2, 0),
                    Decomposition(("a", "c"), (), 2, 0)),
        truncated=True, method="test", enumeration_cap=2)
    assert resolution.certain_rows == ()


def test_both_planted_ambiguous_batches_are_detected(scored):
    _match, ambiguity, _accounting = scored
    assert ambiguity.planted_missed == []
    assert ambiguity.detection_recall == 1.0


def test_the_true_decomposition_is_always_among_the_candidates(scored):
    _match, ambiguity, _accounting = scored
    missing = [sid for sid, found in ambiguity.truth_in_candidates.items() if not found]
    assert not missing, f"true decomposition not enumerated for {missing}"


def test_no_enumeration_was_truncated_on_this_ledger(scored):
    _match, ambiguity, _accounting = scored
    assert ambiguity.truncated == []


# --- the hard postcondition ----------------------------------------------

def test_balance_identity_holds_on_every_determinate_resolution(cascade):
    for item in cascade.stage3.reconstructions:
        if not isinstance(item.resolution, Determinate):
            continue
        proof = item.resolution.proof
        assert proof.holds, f"bank[{item.bank_index}]: {proof.describe()}"
        assert proof.residual == 0
        assert (item.resolution.decomposition.credit_total
                - item.resolution.decomposition.debit_total) == item.bank_amount


def test_the_cascade_reports_zero_balance_violations(cascade):
    assert cascade.balance_violations() == []


def test_a_non_closing_determinate_cannot_be_constructed():
    """A violation is a BUG surfaced loudly, not an exception routed away."""
    with pytest.raises(BalanceViolation):
        Determinate(
            decomposition=Decomposition(("x",), (), 100, 0),
            proof=BalanceProof(bank_amount=999, credit_total=100, debit_total=0,
                               residual=-899, tolerance=0),
            method="test")


# --- DECISIONS.md sec 50: truncated must reflect enumerator status, not cap alone ---

def _budget_exhausted_pool():
    """A pool engineered so the FIRST solve succeeds fast (establishing
    feasibility) but the SECOND, enumerating solve cannot reach `OPTIMAL`
    within a near-zero deterministic-time budget, and finds FEWER than the
    cap before being cut off -- isolating the budget-exhaustion branch from
    the cap-hit branch.
    """
    random.seed(11)
    values = sorted(random.randint(100, 999) for _ in range(30))
    target = sum(values[:15])
    pool = [{"entity_id": f"p{i}", "type": "payment", "credit": v, "debit": 0}
            for i, v in enumerate(values)]
    return pool, target


def test_truncated_reflects_enumerator_status_not_cap_alone():
    """sec 50. An enumeration that exhausts its deterministic-time budget
    before reaching the cap must still report `truncated=True` -- cap-hit
    and budget-exhaustion are both truncation.
    """
    pool, target = _budget_exhausted_pool()
    original_budget = stage3_solver.SOLVER_TIME_LIMIT_SECONDS
    stage3_solver.SOLVER_TIME_LIMIT_SECONDS = 1e-6
    try:
        subsets, truncated, _, _, over_time_budget = enumerate_decompositions(
            pool, target, cap=32)
    finally:
        stage3_solver.SOLVER_TIME_LIMIT_SECONDS = original_budget

    assert len(subsets) < 32, (
        "this fixture must exercise the budget branch, not the cap branch")
    assert over_time_budget, (
        "this fixture must actually exhaust the deterministic-time budget")
    assert truncated, (
        "truncated must be True whenever the enumerator's own status is not "
        "OPTIMAL, even when the cap was never reached")
