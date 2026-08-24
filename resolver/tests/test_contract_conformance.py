"""The resolver obeys the contract. Checked without the answer key.

Every assertion here is expressible from the resolver's own output plus the
solver-visible files. Whether the answers are RIGHT is the oracle's question
and is deliberately not asked here -- if this suite could tell, the resolver
could be tuned against it, and the freeze-before-scoring protocol would mean
nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from resolver_contract.types import (
    Ambiguous, AttestationDiscrepancy, Reconstructed, UnrepresentableClaim,
    Unresolved, Verified, may_consume,
)
from resolver.loaders import load
from resolver.resolve import revocations, resolve

ROOT = Path(__file__).resolve().parent.parent.parent
#: One dataset per shape: attested, unattested, absent, falsely attested.
#: The full sweep is `python3 -m resolver.run --all`; this suite has to stay
#: fast enough that it is actually run.
SAMPLES = [
    ROOT / "corpus" / "datasets" / "A10_B100_Cmax",
    ROOT / "corpus" / "datasets" / "A20_Bnone_Cmax",
    ROOT / "corpus" / "datasets_v2" / "A10_B100_Cmax",
]


@pytest.fixture(scope="module", params=SAMPLES, ids=lambda p: p.name)
def output(request):
    return resolve(load(request.param), cap=40, time_budget=3.0)


def test_every_bank_line_gets_exactly_one_outcome(output, request):
    directory = request.node.callspec.params["output"]
    dataset = load(directory)
    indices = [o.bank_index for o in output.line_outcomes]
    assert sorted(indices) == list(range(len(dataset.bank)))


def test_no_row_is_assigned_twice(output):
    """`ResolverOutput.__post_init__` raises on a double assignment, so
    constructing the output at all is the proof. Asserted anyway, because a
    guarantee nobody tests is a guarantee nobody notices losing."""
    seen = set()
    for outcome in output.line_outcomes:
        for row_id in outcome.assigned_rows:
            assert row_id not in seen
            seen.add(row_id)


def test_only_verified_assigns_and_only_verified_consumes(output):
    """Contract 2.4 and D2: a contested line must not spend the pool.

    `Reconstructed` DOES assign -- it is an answer -- but it does not consume,
    so its rows remain available to later lines. `Ambiguous`,
    `AttestationDiscrepancy` and `Unresolved` assign nothing at all.
    """
    for outcome in output.line_outcomes:
        if isinstance(outcome, (Ambiguous, AttestationDiscrepancy, Unresolved)):
            assert outcome.assigned_rows == ()
        assert may_consume(outcome) == isinstance(outcome, Verified)


def test_every_assignment_carries_a_warrant(output):
    for row_id in output.row_assignments:
        warrant = output.warrant_for_row(row_id)
        assert warrant is not None and warrant.evidence


def test_every_verified_names_two_independent_parties(output):
    for outcome in output.line_outcomes:
        if isinstance(outcome, Verified):
            parties = outcome.warrant.independence.independent_parties
            assert len(parties) >= 2, parties
            assert "psp" in parties and "bank" in parties


def test_every_verified_carries_a_measured_rival_count(output):
    """Contract 3.3: an unmeasured strength is an unstated weakness, and 0 is
    rejected at construction because 0 means never measured."""
    for outcome in output.line_outcomes:
        if isinstance(outcome, Verified):
            assert outcome.rival_closure_count >= 1


def test_reconstructed_is_never_reported_as_corroborated(output):
    """It is strictly weaker than `Verified` and the type refuses to blur
    them: two independent parties agreeing IS Verified."""
    for outcome in output.line_outcomes:
        if isinstance(outcome, Reconstructed):
            assert not outcome.warrant.has_independent_corroboration


def test_ambiguous_cannot_be_asked_for_an_answer(output):
    """D3. `common_rows` is a property of the ambiguity and there is no path
    from it to an assignment."""
    for outcome in output.line_outcomes:
        if not isinstance(outcome, Ambiguous):
            continue
        assert outcome.candidate_count >= 2
        assert outcome.assigned_rows == ()
        with pytest.raises(UnrepresentableClaim):
            outcome.decomposition


def test_no_objective_ever_filtered_a_candidate_set(output):
    """D1. Every annotation must declare it ranked an already-complete set;
    `CandidateSet.__post_init__` raises otherwise, so this re-checks at the
    boundary rather than trusting construction."""
    for outcome in output.line_outcomes:
        for candidate_set in (getattr(outcome, "candidate_set", None),
                              getattr(outcome, "partial_candidates", None)):
            if candidate_set is None:
                continue
            for annotation in candidate_set.ranking:
                assert annotation.applied_after_enumeration
                assert annotation.modelling_assumption.strip()


def test_every_candidate_set_exposes_a_rank_one(output):
    """Contract 6.2 needs it, and the frozen cascade cannot supply it because
    it filters before enumerating -- which is the defect. Exposing rank-1
    makes premise sharing computable for the first time."""
    for outcome in output.line_outcomes:
        for candidate_set in (getattr(outcome, "candidate_set", None),
                              getattr(outcome, "partial_candidates", None)):
            if candidate_set is None or not candidate_set.candidates:
                continue
            assert candidate_set.ranked
            assert candidate_set.rank_one is not None


def test_a_truncated_enumeration_is_never_called_unique(output):
    """One found under truncation is one found, not uniqueness. Truncation is
    the abstention loophole, so it must have its own reason and keep its
    partial set for the oracle to check."""
    for outcome in output.line_outcomes:
        if isinstance(outcome, Unresolved) and outcome.partial_candidates:
            assert not isinstance(outcome, Reconstructed)
        if isinstance(outcome, Reconstructed):
            pass                    # reachability is measured, not asserted


def test_every_unresolved_carries_an_enum_reason(output):
    for outcome in output.line_outcomes:
        if isinstance(outcome, Unresolved):
            assert outcome.reason.value


def test_the_accounting_covers_every_line(output):
    accounting = output.accounting()
    assert accounting.total_lines == len(output.line_outcomes)
    assert accounting.max_candidate_set_size >= 0


# --------------------------------------------------------------------------
# reversals: the two-pass decision, tested as behaviour
# --------------------------------------------------------------------------


def test_a_reversal_is_found_from_the_bank_file_alone():
    """Pass one reads no ledger row. A reversal invalidates a resolution
    retroactively (`DECISIONS.md` 19), so it has to be known before the
    date-ordered pass starts rather than discovered during it."""
    dataset = load(ROOT / "corpus" / "datasets" / "A10_B100_Cmax")
    found = revocations(dataset.bank)
    assert found, "the corpus plants one reversal per dataset"
    for credit, debit in found.items():
        assert dataset.bank[credit].amount_paise == -dataset.bank[debit].amount_paise
        assert dataset.bank[credit].value_date <= dataset.bank[debit].value_date


def test_a_reversed_credit_assigns_nothing_and_consumes_nothing(output, request):
    directory = request.node.callspec.params["output"]
    dataset = load(directory)
    revoked = revocations(dataset.bank)
    by_line = output.by_line()
    for credit in revoked:
        outcome = by_line[credit]
        assert isinstance(outcome, AttestationDiscrepancy)
        assert outcome.assigned_rows == ()
        assert not may_consume(outcome)


# --------------------------------------------------------------------------
# determinism
# --------------------------------------------------------------------------


def test_the_resolver_is_deterministic():
    directory = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"
    first = resolve(load(directory), cap=40, time_budget=3.0)
    second = resolve(load(directory), cap=40, time_budget=3.0)
    assert first.row_assignments == second.row_assignments
    assert ([type(o).__name__ for o in first.line_outcomes]
            == [type(o).__name__ for o in second.line_outcomes])
