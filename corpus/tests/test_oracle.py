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
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.oracle import (determined_instances, reconstructible_instances,   # noqa: E402
                           _itc_risk_flag, score)
from resolver_contract.types import (                           # noqa: E402
    Ambiguous, BreakReason, CandidateSet, Composition, Evidence, EvidenceKind,
    OpenBreak, Reconstructed, ResolverOutput, SourceSystem, Unresolved,
    UnresolvedReason, Verified, Warrant, arithmetic_closure_over,
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


def _reconstruction_warrant() -> Warrant:
    """Unfiltered uniqueness plus cross-line exclusivity, and ONE party.

    Deliberately not corroborated: with no attestation there is no composition
    claim to corroborate, so this can never become `Verified` -- which the
    contract enforces at construction.
    """
    return Warrant.over([
        Evidence(EvidenceKind.UNIQUE_CLOSURE_UNFILTERED,
                 frozenset({SourceSystem.PSP_LEDGER}),
                 "exactly one closing subset, no objective applied"),
        Evidence(EvidenceKind.CROSS_LINE_EXCLUSIVITY,
                 frozenset({SourceSystem.PSP_LEDGER}),
                 "closes no other unexplained credit in the window"),
    ], rationale="arithmetically unique and exclusive; one party, so this is "
                 "strictly weaker than Verified")


def _perfect(truth: dict) -> ResolverOutput:
    """Resolves BOTH gated subpopulations: Verified where attested,
    Reconstructed where not."""
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
    for instance in reconstructible_instances(truth):
        batch = next(b for b in truth["batches"]
                     if b["bank_line_index"] == instance.bank_index)
        outcomes.append(Reconstructed(
            bank_index=instance.bank_index,
            composition=_composition(truth, batch["composition"], rows),
            warrant=_reconstruction_warrant()))
    return ResolverOutput(resolver="perfect-on-both-subpopulations",
                          dataset=dataset.name,
                          line_outcomes=tuple(outcomes))


def _silent(truth: dict) -> tuple[ResolverOutput, int]:
    dataset = a_dataset()
    instances = (list(determined_instances(truth))
                 + list(reconstructible_instances(truth)))
    warrant = Warrant.over([Evidence(
        EvidenceKind.BANK_REFERENCE, frozenset({SourceSystem.BANK}),
        "a credit posted")], rationale="bank only")
    return ResolverOutput(
        resolver="silent", dataset=dataset.name,
        line_outcomes=tuple(
            Unresolved(bank_index=instance.bank_index,
                       reason=UnresolvedReason.ENUMERATION_TRUNCATED,
                       pool_size=60, warrant=warrant)
            for instance in instances)), len(instances)


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


def test_the_abstention_gates_fire_on_a_resolver_that_answers_nothing(truth):
    """THE gates silence cannot pass.

    Every other gate goes to zero for a resolver that returns `Unresolved` to
    everything. If these did too, the oracle would be a certificate of
    abstention rather than an oracle.
    """
    output, count = _silent(truth)
    if not count:
        pytest.skip("this dataset has no gated instance")
    report = score(output, truth)
    gates = report.by_gate()
    assert gates.get("G7", 0) + gates.get("G8", 0) == count, report.render()
    assert set(gates) <= {"G7", "G8"}, (
        "a silent resolver must trip ONLY the abstention gates -- if it trips "
        "others the soundness gates are not measuring soundness")


def test_the_silent_resolver_would_pass_a_soundness_only_oracle(truth):
    """The claim from contract 6.1, asserted rather than argued."""
    output, count = _silent(truth)
    if not count:
        pytest.skip("this dataset has no gated instance")
    report = score(output, truth)
    soundness_only = [v for v in report.violations
                      if v.gate not in ("G7", "G8")]
    assert soundness_only == [], (
        "answering nothing satisfies every soundness gate -- which is exactly "
        "why G7 and G8 exist")


@pytest.mark.parametrize("name", ["A20_B0_Cmax", "A20_B50_Cmax"])
def test_G8_gates_the_cell_that_G7_cannot_reach(name):
    """The measurement that forced the amendment.

    At 0% coverage `determined_instances` is EMPTY, so before G8 existed a
    silent resolver passed every gate on the one axis point that is purely
    about reconstruction.
    """
    dataset = DATASETS / name
    if not (dataset / "ground_truth.json").exists():
        pytest.skip(f"{name} not built")
    truth = json.loads((dataset / "ground_truth.json").read_text())
    reconstructible = reconstructible_instances(truth)
    assert reconstructible, (
        f"{name} has no reconstructible instance, so G8 cannot bite there")
    if name == "A20_B0_Cmax":
        assert not determined_instances(truth), (
            "at 0% coverage nothing can be determined -- that is the gap")


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


# --------------------------------------------------------------------------
# `_itc_risk_flag`'s `actual` set -- DECISIONS.md 88
# --------------------------------------------------------------------------


def _at_risk_month_truth() -> dict:
    """The smallest `truth` shape `_itc_risk_flag` reads: one invoice, one
    ground, one batch, both a payment and a refund settled into it."""
    formed_at = int(datetime(2027, 1, 15, tzinfo=timezone.utc).timestamp())
    return {
        "gst_truth": {"grounds_by_invoice": {"INV1": ["absent_from_gstr2b"]}},
        "itc_at_risk": [{"invoice_no": "INV1", "period": "2027-01"}],
        "batches": [{"settlement_id": "setl_1", "formed_at": formed_at}],
        "settled_in": {"pay_1": "setl_1", "rfnd_1": "setl_1"},
    }


def _one_open_break_flagging_only_the_payment() -> ResolverOutput:
    """What a correct resolver produces on the fixture above: `pay_1` and
    `rfnd_1` land in one break (same reason/age/first_seen), but only
    `pay_1` -- the row that could have generated a gateway fee -- is
    annotated `itc_risk`. `rfnd_1` sits in the break, unflagged, exactly as
    `resolver/breaks.py::_accrues_input_tax` would produce (61)."""
    break_ = OpenBreak(
        row_ids=("pay_1", "rfnd_1"), reason=BreakReason.MISSING_SOURCE,
        age_days=3, first_seen="2027-01-15",
        itc_risk=frozenset({"pay_1"}), itc_risk_grounds=("gstr2b_absent",))
    return ResolverOutput(resolver="fixture", dataset="fixture",
                          line_outcomes=(), unmatched=(break_,))


def test_a_refund_settled_in_an_at_risk_month_is_not_counted_as_a_true_finding():
    """Oracle-side mirror of `resolver/tests/test_gst_risk.py::
    test_a_row_that_never_settled_is_not_flagged_by_its_break_mate` (61). Same
    bug shape, opposite side: that test pins the RESOLVER's `predicted`; this
    one pins the ORACLE's `actual`.

    Before 88, `actual` counted every row settled into an at-risk month
    regardless of type -- `rfnd_1` would have been counted as a true finding
    the resolver should have flagged, producing a false negative on a row
    that could never have carried input tax risk at all. `_is_a_payment_row`
    excludes it from `actual` the same way `_accrues_input_tax` already
    excludes it from `predicted`.
    """
    truth = _at_risk_month_truth()
    output = _one_open_break_flagging_only_the_payment()

    result = _itc_risk_flag(output, truth)

    assert result["true_positive"] == 1
    assert result["false_positive"] == 0
    assert result["false_negative"] == 0
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["open_break_rows"] == 2
    assert result["open_break_rows_payment_type"] == 1


def test_the_refund_test_is_not_vacuous(monkeypatch):
    """Negative control. If `actual` were still built from the untyped
    `universe` -- i.e. if `_is_a_payment_row` degraded to an always-True
    no-op -- `rfnd_1` would reappear in `actual` as a pair `predicted` never
    named, and recall would drop below 1.0. Proves the test above is
    exercising the fix, not passing on an already-empty set."""
    import corpus.oracle as oracle_module

    truth = _at_risk_month_truth()
    output = _one_open_break_flagging_only_the_payment()

    monkeypatch.setattr(oracle_module, "_is_a_payment_row", lambda row_id: True)
    result = oracle_module._itc_risk_flag(output, truth)

    assert result["false_negative"] == 1, (
        "forcing every row to count as a payment should resurrect the "
        "pre-88 false negative on rfnd_1")
    assert result["recall"] == 0.5
