"""The solver contract for class 7.

Written BEFORE any solver exists, so the solver cannot be built wrong.

An ambiguous batch is one where two or more distinct subsets of the eligible
pool achieve the same maximal sum under the live-balance cap. The bank credit
alone does not identify which payments settled. A solver that returns ONE
confident decomposition for such a batch is wrong even when it happens to
name the same subset the simulator picked -- it could not have known.
"""

import pytest

FLAG = "FLAG_AMBIGUOUS"


def ambiguous_batches(truth):
    return [b for b in truth["batches"] if b["ambiguous"]]


# --- the class must exist, by design ---------------------------------------

def test_at_least_one_provably_unresolvable_batch_exists(truth):
    assert len(ambiguous_batches(truth)) >= 1, \
        "class 7 is missing -- the dataset cannot test unresolvability"


def test_each_ambiguous_batch_really_has_multiple_valid_decompositions(truth, rows):
    credits = {r["entity_id"]: r["credit"] for r in rows}
    for batch in ambiguous_batches(truth):
        decompositions = batch["tying_decompositions"]
        assert len(decompositions) >= 2, batch["settlement_id"]
        assert len({tuple(d) for d in decompositions}) == len(decompositions)
        sums = {sum(credits[e] for e in d) for d in decompositions}
        assert len(sums) == 1, "tying subsets must have identical sums"
        assert sums.pop() == batch["selected_payment_credit"]


def test_the_true_decomposition_is_one_of_the_tying_ones(truth):
    for batch in ambiguous_batches(truth):
        assert list(batch["credit_ids"]) in [list(d) for d in
                                             batch["tying_decompositions"]]


def test_ambiguity_is_invisible_in_the_solver_visible_data(rows, truth, bank):
    """Nothing in the shipped data marks an ambiguous batch."""
    flagged = {b["settlement_id"] for b in ambiguous_batches(truth)}
    clean = {b["settlement_id"] for b in truth["batches"]} - flagged
    assert clean, "every batch is ambiguous -- there is nothing to contrast"

    def fingerprint(sid):
        batch_rows = [r for r in rows if r["settlement_id"] == sid]
        return sorted({frozenset(r.keys()) for r in batch_rows}), \
            sorted({r["source_tier"] for r in batch_rows})

    # ambiguous and unambiguous batches are structurally indistinguishable
    assert any(fingerprint(a) == fingerprint(c) for a in flagged for c in clean)
    for row in rows:
        assert "ambiguous" not in str(row).lower()


# --- the contract a solver must satisfy ------------------------------------

def solver_verdict(batch, answer):
    """Score one solver answer for one batch.

    `answer` is either the sentinel FLAG, or a concrete list of entity ids.
    """
    if batch["ambiguous"]:
        return "pass" if answer == FLAG else "fail"
    return "pass" if answer != FLAG and sorted(answer) == sorted(
        batch["credit_ids"]) else "fail"


def test_a_solver_that_flags_ambiguous_batches_passes(truth):
    for batch in ambiguous_batches(truth):
        assert solver_verdict(batch, FLAG) == "pass"


def test_a_confident_single_answer_on_an_ambiguous_batch_FAILS(truth):
    """Even the simulator's own true answer must fail. This is the point."""
    for batch in ambiguous_batches(truth):
        assert solver_verdict(batch, batch["credit_ids"]) == "fail", \
            "a solver returning one confident answer here must not pass"
        for alternative in batch["tying_decompositions"]:
            assert solver_verdict(batch, alternative) == "fail"


def test_flagging_an_unambiguous_batch_also_fails(truth):
    """Flagging everything is not a way to pass."""
    unambiguous = [b for b in truth["batches"] if not b["ambiguous"]]
    assert unambiguous
    for batch in unambiguous:
        assert solver_verdict(batch, FLAG) == "fail"
        assert solver_verdict(batch, batch["credit_ids"]) == "pass"


def test_a_flag_everything_solver_scores_worse_than_chance(truth):
    always_flag = [solver_verdict(b, FLAG) for b in truth["batches"]]
    assert always_flag.count("pass") == len(ambiguous_batches(truth))
    assert always_flag.count("fail") > always_flag.count("pass")
