"""The oracle must detect a known-bad resolver.

Same principle as `--validate-frozen` for the leak audit: an oracle that has
never been shown to fire is not evidence. Each test below builds a synthetic
`ResolverOutput` with ONE specific defect against a real corpus dataset, and
asserts the corresponding gate fires -- and that a correct resolver passes all
of them, so the gates are not simply always-on.

The synthetic resolvers here are the smallest thing that exhibits the defect.
They are not a resolver and are not a sketch of one: no resolver exists yet, by
design (`corpus/CORPUS_SPEC.md` §8).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.oracle import determined_instances, score          # noqa: E402
from resolver_contract.types import (                           # noqa: E402
    Ambiguous, CandidateSet, Composition, Evidence, EvidenceKind, Reconstructed,
    ResolverOutput, SourceSystem, Unresolved, UnresolvedReason, Verified,
    Warrant, arithmetic_closure_over,
)

DATASETS = ROOT / "corpus" / "datasets"


def a_dataset() -> Path:
    candidates = sorted(p for p in DATASETS.iterdir()
                        if (p / "ground_truth.json").exists()
                        and p.name.endswith("B100_Cmax")) if DATASETS.exists() else []
    if not candidates:
        pytest.skip("no corpus dataset built yet")
    return candidates[0]


@pytest.fixture(scope="module")
def truth():
    return json.loads((a_dataset() / "ground_truth.json").read_text())


def _rows(dataset: Path) -> dict[str, dict]:
    items = json.loads((dataset / "recon_combined.json").read_text())["items"]
    return {row["entity_id"]: row for row in items}


def _composition(truth: dict, row_ids, rows) -> Composition:
    credits = tuple(sorted(r for r in row_ids if rows[r]["credit"]))
    debits = tuple(sorted(r for r in row_ids if rows[r]["debit"]))
    return Composition(
        credit_ids=credits, debit_ids=debits,
        credit_total=sum(rows[r]["credit"] for r in credits),
        debit_total=sum(rows[r]["debit"] for r in debits))


def _good_warrant() -> Warrant:
    """Attestation + bank existence + a confirmed consequence. The shape a
    genuine `Verified` needs, and the minimum the contract will construct."""
    return Warrant.over([
        Evidence(EvidenceKind.ATTESTED_SETTLEMENT_ID,
                 frozenset({SourceSystem.PSP_LEDGER}), "settlement report"),
        Evidence(EvidenceKind.BANK_REFERENCE, frozenset({SourceSystem.BANK}),
                 "bank-minted reference"),
        arithmetic_closure_over(
            [SourceSystem.PSP_LEDGER, SourceSystem.BANK],
            detail="the attested rows sum to what the bank actually paid",
            kind=EvidenceKind.ATTESTED_COMPOSITION_CLOSES),
    ], rationale="PSP claims a composition; the bank's amount confirms a "
                 "falsifiable consequence of it")


def _perfect(truth: dict) -> ResolverOutput:
    dataset = a_dataset()
    rows = _rows(dataset)
    outcomes = []
    for instance in determined_instances(truth):
        batch = next(b for b in truth["batches"]
                     if b["bank_line_index"] == instance.bank_index)
        outcomes.append(Verified(
            bank_index=instance.bank_index,
            composition=_composition(truth, batch["composition"], rows),
            warrant=_good_warrant(),
            rival_closure_count=batch["closure"]["count"]))
    return ResolverOutput(resolver="perfect-on-determined",
                          dataset=dataset.name,
                          line_outcomes=tuple(outcomes))


# --------------------------------------------------------------------------


def test_a_correct_resolver_passes_every_gate(truth):
    report = score(_perfect(truth), truth)
    assert report.passed, report.render()


def test_G1_fires_on_a_wrong_verified_composition(truth):
    dataset = a_dataset()
    rows = _rows(dataset)
    instances = determined_instances(truth)
    if not instances:
        pytest.skip("this dataset has no determined instance")
    instance = instances[0]
    batch = next(b for b in truth["batches"]
                 if b["bank_line_index"] == instance.bank_index)
    # drop one true row and add one that does not belong
    kept = list(batch["composition"])[:-1]
    intruder = next(r for r in rows if r not in batch["composition"])
    output = ResolverOutput(
        resolver="confidently-wrong", dataset=dataset.name,
        line_outcomes=(Verified(
            bank_index=instance.bank_index,
            composition=_composition(truth, kept + [intruder], rows),
            warrant=_good_warrant(), rival_closure_count=1),))
    report = score(output, truth)
    assert "G1" in report.by_gate(), report.render()


def test_G3_fires_when_a_complete_candidate_set_omits_the_truth(truth):
    dataset = a_dataset()
    rows = _rows(dataset)
    batch = truth["batches"][0]
    ids = list(rows)[:6]
    output = ResolverOutput(
        resolver="enumerator-is-broken", dataset=dataset.name,
        line_outcomes=(Ambiguous(
            bank_index=batch["bank_line_index"],
            candidate_set=CandidateSet(
                candidates=(_composition(truth, ids[:3], rows),
                            _composition(truth, ids[3:], rows)),
                complete=True, enumeration_cap=32),
            warrant=Warrant.over([Evidence(
                EvidenceKind.BANK_REFERENCE, frozenset({SourceSystem.BANK}),
                "amount only")], rationale="bank only")),))
    report = score(output, truth)
    assert "G3" in report.by_gate(), report.render()


def test_G7_fires_on_a_resolver_that_answers_nothing(truth):
    """THE gate silence cannot pass.

    Every other gate goes to zero for a resolver that returns `Unresolved` to
    everything. If this one did too, the oracle would be a certificate of
    abstention rather than an oracle.
    """
    dataset = a_dataset()
    instances = determined_instances(truth)
    if not instances:
        pytest.skip("this dataset has no determined instance")
    warrant = Warrant.over([Evidence(
        EvidenceKind.BANK_REFERENCE, frozenset({SourceSystem.BANK}),
        "a credit posted")], rationale="bank only")
    output = ResolverOutput(
        resolver="silent", dataset=dataset.name,
        line_outcomes=tuple(
            Unresolved(bank_index=instance.bank_index,
                       reason=UnresolvedReason.ENUMERATION_TRUNCATED,
                       pool_size=60, warrant=warrant)
            for instance in instances))
    report = score(output, truth)
    gates = report.by_gate()
    assert gates.get("G7") == len(instances), report.render()
    assert set(gates) == {"G7"}, (
        "a silent resolver must trip ONLY the abstention gate -- if it trips "
        "others the soundness gates are not measuring soundness")


def test_the_silent_resolver_would_pass_a_soundness_only_oracle(truth):
    """The claim from contract 6.1, asserted rather than argued."""
    dataset = a_dataset()
    instances = determined_instances(truth)
    if not instances:
        pytest.skip("this dataset has no determined instance")
    warrant = Warrant.over([Evidence(
        EvidenceKind.BANK_REFERENCE, frozenset({SourceSystem.BANK}),
        "a credit posted")], rationale="bank only")
    output = ResolverOutput(
        resolver="silent", dataset=dataset.name,
        line_outcomes=tuple(
            Unresolved(bank_index=instance.bank_index,
                       reason=UnresolvedReason.ENUMERATION_TRUNCATED,
                       pool_size=60, warrant=warrant)
            for instance in instances))
    report = score(output, truth)
    soundness_only = [v for v in report.violations if v.gate != "G7"]
    assert soundness_only == [], (
        "answering nothing satisfies every soundness gate -- which is exactly "
        "why G7 exists")


def test_mean_candidate_set_size_is_always_reported(truth):
    """The "enumerate more to score better" loophole, closed unprompted."""
    report = score(_perfect(truth), truth)
    assert "mean_candidate_set_size" in report.measured["accounting"]
    assert "mean candidate set size" in report.render()


def test_balance_identity_violations_are_not_reported(truth):
    """Deliberately absent. Task 4 of the defect report proved the quantity
    structurally incapable of being non-zero, and it was a headline metric in
    two reports anyway."""
    rendered = score(_perfect(truth), truth).render().lower()
    assert "balance-identity" not in rendered
    assert "balance identity" not in rendered
