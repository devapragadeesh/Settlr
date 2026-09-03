"""corpus/oracle.py -- scores a resolver against a corpus dataset.

Consumes `(ResolverOutput, ground_truth)` and **nothing else**. It shares no
code with the generator and none with any resolver: it imports the contract
types, which are interface-only, and reads the ground-truth key as data. If it
shared a helper with the generator, a bug in that helper would be invisible to
both, and the oracle would be scoring the generator's opinion of itself.

## The gated checks, and why each one is gated

**A false `Verified` is THE defect.** Everything else is a measurement. But
soundness gates alone are satisfied by a resolver that answers nothing -- and
enumeration truncates first on the biggest pools, so the most adversarial
cells of the corpus would produce the cleanest numbers in the report. So the
gates come in two kinds, and both are required:

| # | gate | passed by silence? |
|---|---|---|
| G1 | `Verified` assignments that are wrong | yes |
| G2 | `Verified` whose warrant lacks two independent parties | yes |
| G3 | `Ambiguous`/truncated candidate sets missing the truth | yes |
| G4 | rows assigned through a path carrying no warrant | yes |
| G5 | **WITHDRAWN** -- enforced a theorem that is false on the corpus's own data | -- |
| G6 | evidence whose declared provenance the corpus contradicts | yes |
| **G7** | **abstention on a DETERMINED instance** (attested) | **NO** |
| **G8** | **abstention on a RECONSTRUCTIBLE instance** (unattested) | **NO** |

G7 and G8 are the counterweight. Without them the other six are a certificate
of abstention rather than an oracle.

**G8 was added after the corpus was generated, and that is recorded rather than
folded in.** Measured on the built corpus: at 0% attestation coverage
`determined_instances` is EMPTY -- determinedness requires the attestation --
while 11 bank lines still had unique, complete, objective-free closure. So on
the one axis point that is purely about reconstruction, G5 forced
`|Verified| = 0` by theorem and G7 had nothing to range over: **every gate was
vacuous and a silent resolver scored perfectly.** That is sec 6.1's hole
reopened one axis over. G8 closes it, is derived from closure registers already
present in every key, and required no dataset to be regenerated.

## What is deliberately NOT reported

**"Balance-identity violations."** Task 4 of `investigation/DEFECT_REPORT.md`
proved the quantity structurally incapable of being non-zero: every candidate
satisfies `sum == target` by CP-SAT construction, so the residual is
identically zero and the postcondition cannot fire from any code path in the
repository. It was nonetheless a headline metric in two reports. Publishing an
unfalsifiable number as evidence is the same error class as the defects this
corpus exists to find, so it is replaced by three checks that CAN fail:
attestation-composition agreement, bank-reference independence (in
`corpus/leakage_audit.py`), and closure uniqueness measured with no objective.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resolver_contract.types import (          # noqa: E402  interface only
    Ambiguous, AttestationDiscrepancy, CorrectlyUnmatched, DeterminedInstance,
    Evidence, LineOutcome, Reconstructed, ReconstructibleInstance,
    ResolverOutput, SOURCE_PARTY, Unresolved, UnresolvedReason, Verified,
    Warrant,
)

__all__ = ["OracleReport", "score", "determined_instances",
           "reconstructible_instances"]


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------


@dataclass
class Violation:
    gate: str
    bank_index: int | None
    detail: str

    def line(self) -> str:
        where = f"bank[{self.bank_index}]" if self.bank_index is not None else "-"
        return f"  {self.gate:<4} {where:<10} {self.detail}"


@dataclass
class OracleReport:
    dataset: str
    resolver: str
    violations: list[Violation] = field(default_factory=list)
    measured: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.violations

    def by_gate(self) -> dict[str, int]:
        return dict(Counter(v.gate for v in self.violations))

    def render(self) -> str:
        out = [f"# ORACLE -- {self.resolver} on {self.dataset}", ""]
        out += ["## Gated: must be zero", ""]
        gates = {
            "G1": "Verified assignments that are wrong",
            "G2": "Verified whose warrant lacks two independent parties",
            "G3": "candidate sets that do not contain the truth",
            "G4": "rows assigned through a path with no warrant",
            "G5": "WITHDRAWN -- the theorem it enforced was false (contract 6.3)",
            "G6": "evidence provenance the corpus contradicts",
            "G7": "ABSTENTION on a determined instance (attested)",
            "G8": "ABSTENTION on a reconstructible instance (unattested)",
            "G9": "ProvenUnmatched rows that actually settled",
            "G10": "ITC-risk FALSE POSITIVES (vacuous where nothing is flagged)",
        }
        counts = self.by_gate()
        for gate, description in gates.items():
            count = counts.get(gate, 0)
            flag = "FAIL" if count else "ok  "
            out.append(f"  {flag} {gate}  {count:>4}   {description}")
        if self.violations:
            out += ["", "### Violations", ""]
            out += [violation.line() for violation in self.violations[:60]]
            if len(self.violations) > 60:
                out.append(f"  ... and {len(self.violations) - 60} more")

        out += ["", "## Measured, not gated", ""]
        accounting = self.measured.get("accounting", {})
        for name in ("verified", "attestation_discrepancy", "reconstructed",
                     "ambiguous", "unresolved", "proven_unmatched",
                     "open_breaks"):
            out.append(f"  {name:<24} {accounting.get(name, 0)}")
        out += [
            "",
            f"  mean candidate set size  {accounting.get('mean_candidate_set_size', 0):.2f}"
            "   <- reported always, unprompted",
            f"  max candidate set size   {accounting.get('max_candidate_set_size', 0)}",
            f"  incomplete enumerations  {accounting.get('incomplete_enumerations', 0)}",
            f"  Verified non-decisive    {accounting.get('verified_non_decisive', 0)}"
            "   (a rival composition would have passed the same check)",
        ]
        for key, label in (
            ("unresolved_by_reason", "Unresolved by reason"),
            ("reconstructed_accuracy", "Reconstructed correctness (weaker claim)"),
            ("attestation_discrepancy", "AttestationDiscrepancy detected vs planted"),
            ("proven_unmatched", "ProvenUnmatched -- gated by G9"),
            ("open_break", "OpenBreak -- asserts nothing, never gated"),
            ("itc_risk_flag", "ITC risk annotation (measured, NOT gated)"),
            ("foreign_lines", "Foreign bank lines (not ours)"),
            ("premise_sharing", "Premise sharing: rank-1 hit rate vs chance"),
            ("determined", "Determined subpopulation"),
        ):
            value = self.measured.get(key)
            if value:
                out += ["", f"  {label}:"]
                out += [f"    {k}: {v}" for k, v in value.items()]
        out += ["", f"## VERDICT: {'PASS' if self.passed else 'FAIL'}", ""]
        return "\n".join(out)


# --------------------------------------------------------------------------
# ground truth accessors -- read as DATA, never imported from the generator
# --------------------------------------------------------------------------


def determined_instances(truth: dict) -> list[DeterminedInstance]:
    """The subpopulation on which abstention is a defect.

    Built from the corpus key's own closure register, which was produced with
    NO objective and a cap far above any resolver's. `DeterminedInstance`
    refuses construction from a capped enumeration, so the subpopulation cannot
    be quietly widened to flatter a resolver.
    """
    by_line = {batch["bank_line_index"]: batch for batch in truth["batches"]
               if batch.get("bank_line_index") is not None}
    out: list[DeterminedInstance] = []
    for line_index in truth.get("determined_instances", []):
        batch = by_line.get(line_index)
        if batch is None:
            continue
        out.append(DeterminedInstance(
            bank_index=line_index,
            true_composition_row_ids=tuple(sorted(batch["composition"])),
            closure_count=batch["closure"]["count"],
            closure_complete=batch["closure"]["complete"]))
    return out


def reconstructible_instances(truth: dict) -> list[ReconstructibleInstance]:
    """Unattested lines that nonetheless have exactly one explanation.

    `Reconstructed` is achievable on these, so abstaining is a defect (G8).
    `Verified` is not expected -- there is no attestation to corroborate.

    Cross-line exclusivity is computed here rather than read: the subset must
    not also close another settlement's payout in the window. Uniqueness held
    at all three lines that produced the 50 wrong rows, so uniqueness alone
    would rebuild the very failure the contract exists to prevent.
    """
    unattested = set(truth["attestation"]["unattested_settlement_ids"])
    wrong = {item["settlement_id"]
             for item in truth["attestation"]["wrong_attestations"]}
    payouts: dict[str, int] = {batch["settlement_id"]: batch["payout_paise"]
                               for batch in truth["batches"]}
    out: list[ReconstructibleInstance] = []
    for batch in truth["batches"]:
        if batch.get("bank_line_index") is None:
            continue
        if batch["settlement_id"] not in unattested \
                and batch["settlement_id"] not in wrong:
            continue
        register = batch["closure"]
        if register["recoverable"] != "unique" or not register["complete"]:
            continue
        others = [amount for settlement, amount in payouts.items()
                  if settlement != batch["settlement_id"]]
        exclusive = batch["payout_paise"] not in set(others)
        if not exclusive:
            continue
        out.append(ReconstructibleInstance(
            bank_index=batch["bank_line_index"],
            true_composition_row_ids=tuple(sorted(batch["composition"])),
            closure_count=register["count"],
            closure_complete=register["complete"],
            cross_line_exclusive=True))
    return out


def _truth_by_line(truth: dict) -> dict[int, dict]:
    return {batch["bank_line_index"]: batch for batch in truth["batches"]
            if batch.get("bank_line_index") is not None}


def _provenance_party(truth: dict) -> dict[str, str]:
    """source_system -> party, from the corpus provenance graph.

    Contract sec 7: a resolver declares what its evidence rests on; the oracle
    validates that declaration against the graph rather than believing it.
    Otherwise the independence gate checks the resolver's rule against the
    resolver's own self-report, which is a tautology.
    """
    return {entry["source_system"]: entry["party"]
            for entry in truth.get("provenance", {}).values()}


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def score(output: ResolverOutput, truth: dict) -> OracleReport:
    report = OracleReport(dataset=output.dataset, resolver=output.resolver)
    by_line = _truth_by_line(truth)
    bank_truth = {line["line_index"]: line for line in truth["bank_lines"]}
    provenance = _provenance_party(truth)
    coverage = truth["axes"]["B_attestation_coverage_target"]
    wrong_attested = {item["settlement_id"]
                      for item in truth["attestation"]["wrong_attestations"]}

    # ---- G1: a Verified assignment that is wrong -------------------------
    for outcome in output.line_outcomes:
        if not isinstance(outcome, Verified):
            continue
        expected = by_line.get(outcome.bank_index)
        if expected is None:
            report.violations.append(Violation(
                "G1", outcome.bank_index,
                "Verified on a bank line that is not a settlement of ours "
                f"(kind={bank_truth.get(outcome.bank_index, {}).get('kind')})"))
            continue
        claimed = tuple(sorted(outcome.composition.row_ids))
        actual = tuple(sorted(expected["composition"]))
        if claimed != actual:
            missing = sorted(set(actual) - set(claimed))
            extra = sorted(set(claimed) - set(actual))
            report.violations.append(Violation(
                "G1", outcome.bank_index,
                f"Verified composition wrong: {len(extra)} row(s) placed that "
                f"do not belong, {len(missing)} missing. extra={extra[:4]} "
                f"missing={missing[:4]}"))

        # ---- G2: independence, re-checked at the boundary ----------------
        if not outcome.warrant.has_independent_corroboration:
            report.violations.append(Violation(
                "G2", outcome.bank_index,
                "Verified warrant names "
                f"{sorted(outcome.warrant.independence.independent_parties)}"))

        # ---- G5: WITHDRAWN 2026-08-24 ------------------------------------
        #
        # G5 flagged any `Verified` at 0% attestation coverage, on contract
        # 6.3's theorem that no composition claim exists there. The theorem is
        # FALSE on the corpus's own data: axis B varies the bank-line -> batch
        # REFERENCE, and `settlement_id` is populated on 255 of 314 rows of
        # A20_B0_Cmax, with all 12 settlement_report.csv rows present. A
        # composition claim exists, so `Verified` is achievable -- and this
        # gate would have rejected correct answers as contract violations.
        #
        # Left as a comment rather than deleted so the gate numbering in every
        # report stays stable and the withdrawal is visible in the code.

    # ---- G6: declared provenance vs the corpus graph ---------------------
    for outcome in output.line_outcomes:
        for evidence in outcome.warrant.evidence:
            declared = {source.value for source in evidence.derived_from}
            for source in declared:
                corpus_party = provenance.get(source)
                contract_party = SOURCE_PARTY.get(
                    next((s for s in evidence.derived_from
                          if s.value == source), None))
                if corpus_party and contract_party and corpus_party != contract_party:
                    report.violations.append(Violation(
                        "G6", outcome.bank_index,
                        f"{evidence.kind.value} declares source {source!r} as "
                        f"party {contract_party!r}; the corpus provenance "
                        f"graph says {corpus_party!r}"))

    # ---- G3: candidate sets that do not contain the truth ----------------
    #
    # Applied to truncated `Unresolved` as well as `Ambiguous`. A resolver that
    # discards a truncated set has destroyed the evidence of its own miss, and
    # truncation is exactly where the hardest cells live.
    for outcome in output.line_outcomes:
        expected = by_line.get(outcome.bank_index)
        if expected is None:
            continue
        actual = tuple(sorted(expected["composition"]))
        candidate_set = None
        if isinstance(outcome, Ambiguous):
            candidate_set = outcome.candidate_set
        elif isinstance(outcome, Unresolved) and outcome.partial_candidates:
            candidate_set = outcome.partial_candidates
        if candidate_set is None:
            continue
        found = any(tuple(sorted(candidate.row_ids)) == actual
                    for candidate in candidate_set.candidates)
        if not found and candidate_set.complete:
            report.violations.append(Violation(
                "G3", outcome.bank_index,
                f"the truth is absent from a COMPLETE candidate set of "
                f"{candidate_set.size} -- the resolver's enumeration is wrong, "
                "not merely undecided"))
        elif not found:
            report.violations.append(Violation(
                "G3", outcome.bank_index,
                f"the truth is absent from a candidate set of "
                f"{candidate_set.size} (enumeration incomplete)"))

    # ---- G4: an assignment with no warrant -------------------------------
    for row_id in output.row_assignments:
        if output.warrant_for_row(row_id) is None:
            report.violations.append(Violation(
                "G4", None, f"row {row_id} is assigned but carries no warrant"))

    # ---- G7 / G8: abstention where an answer was available ---------------
    determined = determined_instances(truth)
    for bank_index, reason in output.abstention_failures(determined):
        report.violations.append(Violation("G7", bank_index, reason))

    reconstructible = reconstructible_instances(truth)
    for bank_index, reason in output.abstention_failures(reconstructible):
        report.violations.append(Violation(
            "G8", bank_index,
            reason + " -- unattested, but exactly one subset closes and it "
                     "closes nothing else in the window"))

    report.measured = _measure(output, truth, by_line, bank_truth,
                               determined, wrong_attested, reconstructible)
    return report


def _bank_side_planted_indices(truth: dict) -> set[int]:
    """Planted BANK-side attestation discrepancies, as bank-line indices.

    `DECISIONS.md` 56. Read generically from `planted_classes`, mirroring
    `corpus/leakage_audit.py::classes_from_ground_truth` -- no class name is
    hardcoded, so a future bank-side discrepancy class needs no oracle edit.

    `table: "bank"` alone is NOT the qualifying predicate, and 57 records why:
    `d01_settlement_reversal` and `d02_foreign_bank_lines` are also
    `table: "bank"` in all 34 corpus datasets and are not attestation
    discrepancies at all -- a reversal is a correctly recorded reversal and a
    foreign line is somebody else's money. Counting them would publish
    "planted discrepancies the resolver missed" for lines where there is
    nothing to detect. The predicate is structural instead: the class must
    declare, per member, a contradiction between a bank line and a named
    settlement -- i.e. its `detail` entries carry both `bank_line_index` and
    `settlement_id`. Membership itself is still read from `members`, which
    carries the bank-line indices (as strings).
    """
    indices: set[int] = set()
    for spec in truth.get("planted_classes", {}).values():
        if not spec.get("planted", True) or spec.get("table") != "bank":
            continue
        detail = spec.get("detail") or []
        if not detail or not all(
                "bank_line_index" in d and "settlement_id" in d
                for d in detail):
            continue
        for member in spec.get("members", []):
            indices.add(int(member))
    return indices


def _measure(output, truth, by_line, bank_truth, determined,
             wrong_attested, reconstructible=()) -> dict:
    accounting = output.accounting()
    measured: dict = {
        "accounting": {
            "verified": accounting.verified,
            "attestation_discrepancy": accounting.attestation_discrepancy,
            "reconstructed": accounting.reconstructed,
            "ambiguous": accounting.ambiguous,
            "unresolved": accounting.unresolved,
            "proven_unmatched": accounting.proven_unmatched,
            "open_breaks": accounting.open_breaks,
            "mean_candidate_set_size": accounting.mean_candidate_set_size,
            "max_candidate_set_size": accounting.max_candidate_set_size,
            "incomplete_enumerations": accounting.incomplete_enumerations,
            "verified_non_decisive": accounting.verified_non_decisive,
        },
        "unresolved_by_reason": accounting.reasons.get("unresolved", {}),
    }

    # --- Reconstructed correctness. A WEAKER claim, so a nonzero error rate
    # --- here is a finding rather than a build failure.
    right = wrong = 0
    for outcome in output.line_outcomes:
        if not isinstance(outcome, Reconstructed):
            continue
        expected = by_line.get(outcome.bank_index)
        actual = tuple(sorted(expected["composition"])) if expected else ()
        if tuple(sorted(outcome.composition.row_ids)) == actual:
            right += 1
        else:
            wrong += 1
    measured["reconstructed_accuracy"] = {
        "correct": right, "wrong": wrong,
        "note": "a weaker claim than Verified, so errors here are MEASURED, "
                "not gated -- but they are still errors and are reported"}

    # --- AttestationDiscrepancy: detected vs planted ----------------------
    #
    # TWO REFERENCE FRAMES, kept apart on purpose. `wrong_attested` is a set of
    # SETTLEMENT IDS (the PSP attested a wrong amount). A bank-side planted
    # class lives in BANK-LINE-INDEX space (the bank posted a wrong amount for
    # a settlement whose own record is correct). DECISIONS.md 56 fixes the
    # accounting for the second frame and explicitly REJECTS mapping one frame
    # into the other through `by_line`: a bank line's index and the settlement
    # it happens to correspond to are not interchangeable keys (see 44).
    bank_side_planted_indices = _bank_side_planted_indices(truth)
    planted = len(wrong_attested) + len(bank_side_planted_indices)
    detected = [o for o in output.line_outcomes
                if isinstance(o, AttestationDiscrepancy)]
    true_positive = 0
    for outcome in detected:
        expected = by_line.get(outcome.bank_index)
        # frame 1: settlement-id space -- the PSP attested wrongly
        psp_side = bool(expected and expected["settlement_id"] in wrong_attested)
        # frame 2: bank-line-index space -- the bank posted wrongly (56)
        bank_side = outcome.bank_index in bank_side_planted_indices
        if psp_side or bank_side:
            true_positive += 1
    # FOUR-WAY, not two-way. "reported minus planted" reads as a false-alarm
    # rate to anyone skimming, and it is not one: a bank debit revoking an
    # earlier credit IS a cross-party contradiction, it is simply not one the
    # corpus planted. The corpus records reversals as `reversal_debit` bank
    # lines naming their settlement, so this is CHECKED rather than asserted.
    reversed_settlements = {line["true_settlement_id"]
                            for line in truth["bank_lines"]
                            if line["kind"] == "reversal_debit"
                            and line["true_settlement_id"]}
    other_kind = genuinely_false = 0
    false_detail: list[str] = []
    for outcome in detected:
        expected = by_line.get(outcome.bank_index)
        settlement = expected["settlement_id"] if expected else None
        # frame 1: a planted PSP-side wrong attestation -- a correct detection
        if settlement in wrong_attested:
            continue
        # frame 2: a planted BANK-side mispost -- also a correct detection, and
        # before 56 it fell through to `genuinely_false` for want of a
        # settlement id to be found by. Kept as its own branch, not folded into
        # the condition above, so the frame distinction stays visible.
        if outcome.bank_index in bank_side_planted_indices:
            continue
        kind = outcome.contradiction.kind.value
        corroborated = (kind == "credit_reversed"
                        and settlement in reversed_settlements)
        if corroborated:
            other_kind += 1
        else:
            genuinely_false += 1
            false_detail.append(f"bank[{outcome.bank_index}] {kind}")
    missed = sorted(wrong_attested - {
        by_line[o.bank_index]["settlement_id"] for o in detected
        if by_line.get(o.bank_index)})
    # frame 2's misses, reported in BANK-LINE-INDEX space as their own
    # collection (56). They are deliberately NOT coerced into `missed`'s
    # settlement-id shape -- the two are not the same kind of thing, and a
    # reader must not be able to read one as the other.
    missed_bank_side = sorted(
        bank_side_planted_indices - {o.bank_index for o in detected})
    measured["attestation_discrepancy"] = {
        "planted": planted, "reported": len(detected),
        "correctly_identified": true_positive,
        "true_finding_of_another_kind": other_kind,
        "genuinely_false": genuinely_false,
        "genuinely_false_detail": false_detail,
        "planted_but_missed": missed,
        "planted_but_missed_bank_side": missed_bank_side,
        "false_findings": len(detected) - true_positive,
        "note": "FOUR-WAY. `false_findings` is retained for continuity and is "
                "MISLEADING on its own: it is reported minus planted, and a "
                "reversal corroborated by a reversal_debit line in the answer "
                "key is a true finding of a kind the corpus did not plant. "
                "`genuinely_false` is the false-alarm count. TWO FRAMES: "
                "`planted_but_missed` is settlement ids (PSP attested "
                "wrongly); `planted_but_missed_bank_side` is bank-line "
                "indices (the bank posted wrongly). DECISIONS.md 56"}

    # --- G9: a ProvenUnmatched row that actually settled ------------------
    # Contract 4.7.1. Until this gate existed, "0 wrong answers" in every
    # report in this repository meant "0 wrong Verified" ONLY, while a second
    # outcome type that also asserted something was wrong 2,469 times and
    # nothing looked at it. G9 closes that hole and is zero-tolerance.
    reason_of = truth.get("unsettled_reason", {})
    settled_in = truth.get("settled_in", {})
    proven_rows = proven_wrong = 0
    for item in output.proven_unmatched:
        for row_id in item.row_ids:
            proven_rows += 1
            if reason_of.get(row_id) is None:
                proven_wrong += 1
                report.violations.append(Violation(
                    "G9", -1,
                    f"ProvenUnmatched({item.reason.value}) claims the ledger "
                    f"entails no bank credit for {row_id}, which settled in "
                    f"{settled_in.get(row_id)}"))

    # Is the ENTAILMENT'S OWN reason right, over rows that did not settle?
    proven_map = {"netted_out": "netted_out_by_full_refund",
                  "not_captured": "not_captured"}
    pu_right = pu_wrong = 0
    for item in output.proven_unmatched:
        for row_id in item.row_ids:
            actual = reason_of.get(row_id)
            if actual is None:
                continue
            if proven_map.get(item.reason.value) == actual:
                pu_right += 1
            else:
                pu_wrong += 1
    measured["proven_unmatched"] = {
        "rows": proven_rows, "row_settled_after_all": proven_wrong,
        "reason_correct": pu_right, "reason_wrong": pu_wrong,
        "note": "GATED at zero by G9. A positive claim, unlike OpenBreak"}

    # --- OpenBreak: NEVER scored for correctness, only described ----------
    # It asserts nothing, so there is nothing here to be right or wrong about.
    # What IS reported is whether the queue is usable: how it clusters, how it
    # ages, and how many rows the resolver could not classify at all.
    ages: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    causes: set[int] = set()
    clustered = settled_rows = 0
    for item in output.open_breaks:
        n = len(item.row_ids)
        by_reason[item.reason.value] = by_reason.get(item.reason.value, 0) + n
        ages[item.age_bucket] = ages.get(item.age_bucket, 0) + n
        if item.caused_by is not None:
            causes.add(item.caused_by)
            clustered += n
        settled_rows += sum(1 for r in item.row_ids if reason_of.get(r) is None)
    measured["open_break"] = {
        "rows": sum(len(i.row_ids) for i in output.open_breaks),
        "by_reason": by_reason, "by_age": ages,
        "clustered_rows": clustered, "distinct_causes": len(causes),
        "rows_per_cause": round(clustered / len(causes), 1) if causes else 0.0,
        "rows_that_did_settle": settled_rows,
        "note": "NOT GATED and not scored for correctness -- an OpenBreak "
                "asserts nothing. `rows_that_did_settle` is descriptive: those "
                "rows are correctly OPEN, not correctly explained"}

    # --- ITC risk annotation on OpenBreak ---------------------------------
    # Precision is GATED by G10; recall is measured and deliberately not.
    # `DECISIONS.md` 60 refused to gate this at all, on the grounds that
    # gating an untested reimplementation's FIRST numbers is the G5 mistake.
    # That objection expired: 61 fixed the frame the 0.0 exposed, and 68/73
    # stabilised the budget the numbers were queued behind.
    #
    # READ THE VACUITY WARNING BELOW BEFORE QUOTING THIS GATE. On both
    # `datasets_gst` points the flag fires on NOTHING -- 0 of 22 and 0 of 18
    # open-break rows -- so there are no predictions to be false and G10
    # cannot fail there. It is a REGRESSION GUARD against a future
    # `resolver/breaks.py` that flags more aggressively, not a check the
    # current implementation passes on its merits. Recall stays ungated
    # because the population is far too small for a miss to mean anything:
    # the held-out run's recall of 0.75 is three true positives and one
    # false negative.
    if "gst_truth" in truth:
        flag = _itc_risk_flag(output, truth)
        measured["itc_risk_flag"] = flag
        flag["gate"] = ("G10 gates false_positive at zero. VACUOUS where "
                        "flagged_rows is 0: no prediction can be false. "
                        "Recall is NOT gated")
        for _ in range(flag.get("false_positive", 0)):
            report.violations.append(Violation(
                "G10", None,
                f"ITC risk flagged a (row, ground) pair the key does not "
                f"carry -- {flag['false_positive']} false positive(s) over "
                f"{flag['flagged_rows']} flagged row(s)"))

    # --- foreign bank lines: can the resolver say "not ours"? -------------
    foreign = [index for index, line in bank_truth.items()
               if line["kind"] != "settlement"]
    adopted = [o.bank_index for o in output.line_outcomes
               if o.bank_index in foreign and o.assigned_rows]
    measured["foreign_lines"] = {
        "in_file": len(foreign), "falsely_adopted": len(adopted),
        "note": "no analogue exists in the frozen set, whose bank statement is "
                "a bijection with the batch list"}

    # --- the premise-sharing statistic (contract 6.2) ---------------------
    measured["premise_sharing"] = _premise_sharing(output, truth, by_line)

    # --- the determined subpopulation ------------------------------------
    resolved = sum(1 for instance in determined
                   if isinstance(output.by_line().get(instance.bank_index),
                                 (Verified, Reconstructed)))
    rebuilt = sum(1 for instance in reconstructible
                  if isinstance(output.by_line().get(instance.bank_index),
                                Reconstructed))
    measured["determined"] = {
        "determined_instances": len(determined), "determined_resolved": resolved,
        "determined_abstained": len(determined) - resolved,
        "reconstructible_instances": len(reconstructible),
        "reconstructible_resolved": rebuilt,
        "reconstructible_abstained": len(reconstructible) - rebuilt,
        "note": "the subpopulations the corpus PROVES have an answer. "
                "Abstention here is gated at zero (G7 attested, G8 "
                "unattested) and these are the only gates silence cannot pass"}
    return measured


#: The reporting timezone the whole corpus is generated in. Declared here
#: rather than imported: the oracle shares no helper with the generator, and a
#: shared offset constant would make an offset bug invisible to both sides.
_IST = timezone(timedelta(hours=5, minutes=30))

#: `ground_truth.json`'s statutory reason string -> the resolver's ground name.
#: Two independent vocabularies for one set of statutes, related by a table
#: rather than by a shared enum, for the same reason.
_REASON_TO_GROUND = {
    "absent_from_gstr2b": "gstr2b_absent",
    "no_irn_on_notified_supplier_invoice": "gstr2b_no_irn",
    "supplier_gstr3b_not_filed_rule_37a": "gstr2b_37a_exposure",
}

#: `corpus/generator/build.py:386/409/429` mints row ids under exactly these
#: three prefixes for payment/refund/adjustment rows respectively. Not an
#: asserted contract anywhere else in this module before 88 --
#: `corpus/tests/test_conformance.py::
#: test_itc_risk_actual_only_admits_payment_row_ids` pins it against a real
#: generated fixture so a future rename fails loudly here rather than
#: silently turning `_is_a_payment_row` into a no-op or an over-broad filter.
_PAYMENT_PREFIX = "pay_"


def _is_a_payment_row(row_id: str) -> bool:
    """Did this row-id come from a PAYMENT, as opposed to a refund or an
    adjustment? DECISIONS.md 88.

    This is the oracle-side mirror of ONE leg of
    `resolver/breaks.py::_accrues_input_tax` (61) -- the `type == "payment"`
    leg, and ONLY that leg. `corpus/oracle.py::score()` receives a
    `ResolverOutput` and the parsed `ground_truth.json` and nothing else; no
    row's `fee` or `tax` ever reaches this module (verified: `grep -n
    '"fee"\\|"tax"' corpus/oracle.py` matches nothing outside this
    docstring). A refund or adjustment settling into an at-risk month
    therefore cannot be told apart from a payment by the `settled_at`/`fee`/
    `tax` legs `_accrues_input_tax` also checks -- this predicate is a
    CEILING, not an approximation of the full resolver-side check, and
    88 records that ceiling as a deliberate, not-yet-closed gap rather than
    something this predicate quietly papers over.

    A refund never carries a gateway fee -- there is no supply for the
    gateway to invoice -- so a refund settling into an at-risk month carries
    no input tax at risk regardless of which statutory ground the month
    carries. Same reasoning for an adjustment. 61 made the identical argument
    resolver-side, applied to `predicted`; this is its mirror, applied to
    `actual`.
    """
    return row_id.startswith(_PAYMENT_PREFIX)


def _itc_risk_flag(output, truth) -> dict:
    """Precision/recall of `OpenBreak.itc_risk` / `.itc_risk_grounds`.

    MEASURED, NOT GATED, and `DECISIONS.md` 60 records why at length. In one
    line: this is the first contact between `resolver/` and `gstr2b.csv` in
    any form, `resolver/breaks.py` reimplements the gateway-GSTIN
    identification and the three statutory checks rather than importing the
    frozen reference (an accepted duplication-drift risk, 59), and gating an
    untested reimplementation's FIRST measured numbers is exactly the mistake
    G5 was withdrawn for. A number has to exist before a threshold on it can
    mean anything.

    ## The two frames, and why the disagreement between them is the finding

    The resolver's claim is per ROW: "this row belongs to a settled month
    carrying an ITC finding". It attributes a row to a month by
    `first_reconcilable` -- deliberately NOT `settled_at`, because every row
    reaching `dispositions()` is a row nothing placed and `settled_at` is an
    unconfirmed PSP claim on such a row (59 records that choice and its
    reason).

    The truth here is built in the OTHER frame, from the key alone and with no
    reference to that choice: `settled_in` names the batch a row genuinely
    landed in, `batches[].formed_at` dates that batch, and `itc_at_risk` names
    the periods carrying a finding. A row that never settled has no month in
    this frame at all -- and correctly so, because the gateway never invoiced a
    fee for it, so there is no input tax on it to be at risk.

    Scoring one frame against the other is the point, not a defect in the
    measurement. Forcing them into a common frame -- e.g. re-deriving truth
    from `first_reconcilable` too -- would make the row->month attribution
    shared between the thing measured and the thing measuring it, and the
    statistic would then be unable to see an attribution error at all. That is
    44's named defect class and 56 already rejected the same move once.

    ## Scope, stated rather than implied

    The universe is the rows that appear in some `OpenBreak`, because that is
    the only place the resolver may put this annotation (59 confines GST
    evidence to `OpenBreak` outright). A row the resolver correctly settled is
    neither flagged nor flaggable, and counting it as a false negative would
    measure the contract's own restriction rather than the flag.

    `precision` and `recall` are `None`, never 1.0, when their denominator is
    empty. An undefined recall is reported as undefined.

    Pairs are `(row_id, ground)`. `itc_risk_grounds` is a per-BREAK union, so a
    break whose flagged rows straddled two at-risk months would attribute both
    months' grounds to every flagged row in it; `breaks_straddling_months`
    counts how often that could have happened, so the reader can see whether
    the cross-product is lossy on this data rather than trusting that it isn't.

    `actual` is additionally scoped to rows `_is_a_payment_row` admits
    (`DECISIONS.md` 88). This mirrors 61's fix on the `predicted` side, but
    reaches only the `type` leg of `_accrues_input_tax` -- this module has no
    access to `fee`/`tax` truthy-ness. A refund or adjustment that settled
    into an at-risk month is therefore never counted as a true finding here,
    matching the resolver's own inability to flag it. `universe` itself is
    left type-agnostic -- it feeds purely descriptive counts
    (`open_break_rows_settled_in_truth`, `flagged_rows_that_never_settled`)
    that are legitimately about every open-break row regardless of type.
    """
    gst_truth = truth["gst_truth"]
    # invoice -> filing period. Same source `corpus/score_gst.py` already uses
    # to turn a period back into an invoice for the frozen filters; read in the
    # other direction here.
    invoice_period = {item["invoice_no"]: item["period"]
                      for item in truth.get("itc_at_risk", [])}
    at_risk: dict[str, set[str]] = {}
    unmapped: list[str] = []
    for invoice_no, reasons in gst_truth["grounds_by_invoice"].items():
        period = invoice_period.get(invoice_no)
        if period is None:
            unmapped.append(invoice_no)
            continue
        for reason in reasons:
            ground = _REASON_TO_GROUND.get(reason)
            if ground is not None:
                at_risk.setdefault(period, set()).add(ground)

    month_of_batch = {batch["settlement_id"]:
                      datetime.fromtimestamp(batch["formed_at"],
                                             _IST).strftime("%Y-%m")
                      for batch in truth["batches"]}
    settled_in = truth.get("settled_in", {})

    def truth_month(row_id: str):
        return month_of_batch.get(settled_in.get(row_id))

    universe = sorted({row_id for item in output.open_breaks
                       for row_id in item.row_ids})
    payment_universe = sorted(r for r in universe if _is_a_payment_row(r))
    predicted: set[tuple[str, str]] = set()
    straddling = 0
    for item in output.open_breaks:
        if len({truth_month(r) for r in item.row_ids
                if truth_month(r) is not None}) > 1:
            straddling += 1
        for row_id in item.itc_risk:
            for ground in item.itc_risk_grounds:
                predicted.add((row_id, ground))
    actual = {(row_id, ground) for row_id in payment_universe
              for ground in at_risk.get(truth_month(row_id) or "", ())}

    tp = len(predicted & actual)
    fp = len(predicted - actual)
    fn = len(actual - predicted)
    flagged = {row_id for item in output.open_breaks for row_id in item.itc_risk}
    return {
        "open_break_rows": len(universe),
        "open_break_rows_payment_type": len(payment_universe),
        "open_break_rows_settled_in_truth":
            sum(1 for r in universe if truth_month(r) is not None),
        "flagged_rows": len(flagged),
        "flagged_rows_that_never_settled":
            sum(1 for r in flagged if truth_month(r) is None),
        "breaks_straddling_months": straddling,
        "at_risk_months": {month: sorted(grounds)
                           for month, grounds in sorted(at_risk.items())},
        "invoices_with_no_period_in_key": sorted(unmapped),
        "true_positive": tp, "false_positive": fp, "false_negative": fn,
        "precision": None if tp + fp == 0 else round(tp / (tp + fp), 4),
        "recall": None if tp + fn == 0 else round(tp / (tp + fn), 4),
        "note": "measured, not gated -- first contact between resolver/ and "
                "gstr2b.csv, no prior baseline exists to gate against "
                "(mirrors reconstructed_accuracy and this repo's own G5 "
                "withdrawal). Truth is in the SETTLED-month frame read from "
                "the key; the resolver attributes by first_reconcilable. A "
                "row that never settled accrued no gateway fee and so carries "
                "no input tax to be at risk",
    }


def _premise_sharing(output, truth, by_line) -> dict:
    """Rank-1 hit rate in excess of chance, over multi-closure instances.

    The only falsifiable form of the premise-sharing test. "Scores flat across
    the three selection rules" is unfalsifiable on its own: under
    `random_valid` at large pools a SOUND resolver returns `Ambiguous` almost
    everywhere, so every outcome-level metric is flat under both hypotheses.

    The ranking, by contrast, exists on every instance including the ones
    correctly declined. Under the null -- no shared premise -- the rank-1 pick
    is right with probability `1/k` and the excess is 0 for all three rules.
    Under premise sharing it is strongly positive for `max_under_cap`.

    Instances whose closure register hit the cap are EXCLUDED and the exclusion
    is reported: `k` would be a lower bound there, so `1/k` would be an
    overestimate of chance and the excess would be flattered.
    """
    hits = trials = 0
    chance = 0.0
    excluded_capped = excluded_unranked = 0
    for outcome in output.line_outcomes:
        expected = by_line.get(outcome.bank_index)
        if expected is None:
            continue
        register = expected["closure"]
        if register["count"] < 2:
            continue
        if not register["complete"]:
            excluded_capped += 1
            continue
        candidate_set = getattr(outcome, "candidate_set", None) \
            or getattr(outcome, "partial_candidates", None)
        if candidate_set is None or not candidate_set.ranked:
            excluded_unranked += 1
            continue
        pick = candidate_set.rank_one
        if pick is None:
            excluded_unranked += 1
            continue
        trials += 1
        chance += 1 / register["count"]
        hits += tuple(sorted(pick.row_ids)) == tuple(sorted(expected["composition"]))
    if not trials:
        return {"multi_closure_instances_scored": 0,
                "excluded_enumeration_capped": excluded_capped,
                "excluded_resolver_did_not_rank": excluded_unranked,
                "note": "no scoreable instance: the resolver exposed no ranking, "
                        "so premise sharing cannot be measured on this run"}
    return {
        "multi_closure_instances_scored": trials,
        "rank1_hit_rate": round(hits / trials, 4),
        "chance_rate_mean_1_over_k": round(chance / trials, 4),
        "excess_over_chance": round(hits / trials - chance / trials, 4),
        "excluded_enumeration_capped": excluded_capped,
        "excluded_resolver_did_not_rank": excluded_unranked,
        "note": "0 under the null for every selection rule; positive means the "
                "resolver's objective agrees with the generator's rule more "
                "often than chance (contract 6.2)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True,
                        help="a serialised ResolverOutput (JSON)")
    arguments = parser.parse_args()
    truth = json.loads((arguments.dataset / "ground_truth.json").read_text())
    # A resolver ships its own serialiser; the oracle only needs the shape.
    raise SystemExit("load your ResolverOutput and call score(); no resolver "
                     "exists yet by design -- see resolver_contract/"
                     "RESOLVER_CONTRACT.md and corpus/CORPUS_SPEC.md")


if __name__ == "__main__":
    raise SystemExit(main())
