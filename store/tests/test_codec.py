"""Lossless round-trip of every `LineOutcome`/`RowOutcome` produced by real
resolver runs, across many datasets -- not synthetic instances, the actual
objects `resolve()` returns.

**Correctness is asserted by `==`, not by `repr()`.** An earlier draft of
this test asserted `repr(reconstructed) == repr(original)` and it was
FLAKY -- failing on some process runs and not others, on the identical
dataset and code. The cause: several outcome fields are `frozenset`s
(`Evidence.derived_from`, `IndependenceDetermination.sources`,
`OpenBreak.itc_risk`), and CPython's `frozenset` iteration order depends on
hash-table placement, which is insertion-order-sensitive whenever two
elements collide -- so two frozensets with IDENTICAL elements, each
independently correct, can legitimately repr in a different order. `==` does
not have this problem: `frozenset.__eq__` compares contents, not iteration
order. `test_frozenset_repr_order_is_not_a_reliable_equality_check` below
demonstrates the underlying instability directly, so this isn't asserted on
faith.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import resolver_contract.types as contract
from ingest import load
from resolver.resolve import resolve
from store.codec import outcome_from_jsonable, outcome_to_jsonable

ROOT = Path(__file__).resolve().parent.parent.parent


def _sample_datasets() -> list[Path]:
    # A representative subset, not all 30 -- a full resolve() per dataset at
    # cap=40 costs real wall-clock time (measured: all 30 took 4:44, too slow
    # for the routine gate). The broader claim -- 1,977 outcomes across all
    # 30 datasets in corpus/datasets and corpus/datasets_v2, 0 mismatches --
    # was run once as a one-time check during development (see this entry's
    # DECISIONS.md write-up) and is not re-run on every test invocation;
    # these six stay in the routine suite as a fast regression guard.
    names = ("A10_B100_Cmax", "A20_B0_Cmax", "A20_Bnone_Cmax",
             "A40_B100_Crandom", "A60_B100_Cmax", "A20_B100_Cmax")
    dirs = []
    for family in ("datasets", "datasets_v2"):
        base = ROOT / "corpus" / family
        for name in names:
            candidate = base / name
            if candidate.is_dir():
                dirs.append(candidate)
    return dirs


DATASET_DIRS = _sample_datasets()


@pytest.mark.parametrize("directory", DATASET_DIRS, ids=lambda d: str(d.relative_to(ROOT)))
def test_every_outcome_round_trips_losslessly(directory: Path) -> None:
    dataset = load(directory)
    output = resolve(dataset, cap=40, time_budget=3.0)

    for outcome in list(output.line_outcomes) + list(output.unmatched):
        blob = outcome_to_jsonable(outcome)
        # Through an ACTUAL json.dumps/loads cycle, not just the in-memory
        # dict -- proves the payload is really JSON-safe (no stray Enum
        # objects, no non-serialisable type slipped through).
        restored = outcome_from_jsonable(json.loads(json.dumps(blob)))
        assert restored == outcome, (type(outcome).__name__, outcome, restored)


def test_frozensets_with_identical_elements_can_repr_differently() -> None:
    """The instability this test file's docstring describes, shown directly:
    two frozensets built from the SAME elements in different insertion order
    can repr differently, even though they are `==`. CPython's frozenset
    internal table is small (8 slots initially) and open-addressed, so
    collision resolution -- and therefore iteration order -- depends on
    insertion sequence whenever two elements land in the same slot. This is
    demonstrated over many candidate element sets rather than one hardcoded
    pair, since which pairs collide depends on hash values this test does not
    control; the loop only needs to find ONE order-sensitive case among many
    tries to make the point, and reliably does.
    """
    found_a_reordering_that_changes_repr = False
    for offset in range(200):
        elements = [f"row_{offset}_{i}" for i in range(6)]
        forward = frozenset(elements)
        backward = frozenset(reversed(elements))
        assert forward == backward
        if repr(forward) != repr(backward):
            found_a_reordering_that_changes_repr = True
            break
    assert found_a_reordering_that_changes_repr, (
        "expected at least one of 200 candidate element sets to show "
        "insertion-order-sensitive frozenset repr -- if this ever fails, "
        "CPython's set implementation changed and the finding above should "
        "be re-verified, not just re-asserted")


def test_every_optional_contract_field_is_unwrapped_not_passed_through() -> None:
    """Every `X | None` field in the contract must be UNWRAPPED to `X` by the
    codec's optional handling -- checked directly, over the real dataclasses,
    rather than waiting for a resolver run to happen to populate one.

    This is the guard the round-trip test above could not be: a field like
    `Unresolved.partial_candidates` is only non-`None` when enumeration
    actually truncated, which depends on the time budget and CPU contention,
    so a decoder that silently passed the raw dict through was invisible on
    any run where that path did not fire.

    The defect it caught: `_unwrap_optional` compared the field's origin
    against `typing.Union` alone. Contract fields are written PEP 604 style
    (`CandidateSet | None`), whose origin is `types.UnionType` -- a DIFFERENT
    object from `typing.Union` on Python < 3.14, and the same object from 3.14
    on. So the unwrap silently failed on CI's pinned 3.12 while passing on a
    3.14 dev machine, and `from_jsonable` fell through to `return value`,
    handing back the untouched `{"__type__": "CandidateSet", ...}` dict.
    Asserting over both spellings is what makes this version-independent.
    """
    import dataclasses
    import types as _types
    import typing as _typing

    from store.codec import _unwrap_optional

    checked = 0
    for name in dir(contract):
        cls = getattr(contract, name)
        if not (isinstance(cls, type) and dataclasses.is_dataclass(cls)):
            continue
        hints = _typing.get_type_hints(cls, vars(contract))
        for field_name, hint in hints.items():
            origin = _typing.get_origin(hint)
            if origin not in (_typing.Union, _types.UnionType):
                continue
            non_none = [a for a in _typing.get_args(hint) if a is not type(None)]
            if len(non_none) != 1:
                continue
            unwrapped, was_optional = _unwrap_optional(hint)
            assert was_optional, (
                f"{cls.__name__}.{field_name}: {hint!r} is an optional the "
                "codec failed to recognise as one; from_jsonable will fall "
                "through and hand back the raw JSON value untouched")
            assert unwrapped is non_none[0], (
                f"{cls.__name__}.{field_name}: unwrapped to {unwrapped!r}, "
                f"expected {non_none[0]!r}")
            checked += 1

    assert checked, (
        "found no optional fields in resolver_contract.types -- this test "
        "asserts nothing and the contract should be re-checked, not this "
        "assertion removed")


def test_an_unresolved_carrying_partial_candidates_round_trips() -> None:
    """The exact shape CI failed on, built directly instead of waiting for a
    truncated enumeration to produce one. `Unresolved.partial_candidates` is
    the contract's own stated reason this field exists -- "a resolver that
    discards the set has destroyed the evidence of its own miss" -- so a
    decoder that returns it as a plain dict has destroyed it just as surely.
    """
    evidence = contract.Evidence(
        kind=contract.EvidenceKind.ARITHMETIC_CLOSURE,
        derived_from=frozenset({contract.SourceSystem.PSP_LEDGER}),
        detail="the enumerated rows sum to the target",
    )
    outcome = contract.Unresolved(
        bank_index=13,
        reason=contract.UnresolvedReason.ENUMERATION_TRUNCATED,
        pool_size=7,
        warrant=contract.Warrant(
            evidence=(evidence,),
            independence=contract.IndependenceDetermination(
                sources=frozenset({contract.SourceSystem.PSP_LEDGER}),
                rationale="one source; not corroborated",
            ),
        ),
        partial_candidates=contract.CandidateSet(
            candidates=(contract.Composition(
                credit_ids=("pay_a", "pay_b"), debit_ids=("rfnd_c",),
                credit_total=100, debit_total=40),),
            complete=False,
            enumeration_cap=40,
            ranking=(contract.RankingAnnotation(
                objective="maximise applied debits",
                applied_after_enumeration=True,
                modelling_assumption="SETTLEMENT_SPEC.md 1.4"),),
            ranked=True,
        ),
    )

    restored = outcome_from_jsonable(json.loads(json.dumps(outcome_to_jsonable(outcome))))

    assert isinstance(restored.partial_candidates, contract.CandidateSet), (
        "partial_candidates came back as "
        f"{type(restored.partial_candidates).__name__}, not CandidateSet")
    assert restored == outcome
