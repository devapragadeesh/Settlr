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
                     "ambiguous", "unresolved", "correctly_unmatched"):
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
            ("correctly_unmatched", "CorrectlyUnmatched reason accuracy"),
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
            "correctly_unmatched": accounting.correctly_unmatched,
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
    planted = len(truth["attestation"]["wrong_attestations"])
    detected = [o for o in output.line_outcomes
                if isinstance(o, AttestationDiscrepancy)]
    true_positive = 0
    for outcome in detected:
        expected = by_line.get(outcome.bank_index)
        if expected and expected["settlement_id"] in wrong_attested:
            true_positive += 1
    measured["attestation_discrepancy"] = {
        "planted": planted, "reported": len(detected),
        "correctly_identified": true_positive,
        "false_findings": len(detected) - true_positive,
        "note": "the highest-value output the contract defines, and the one "
                "the old engine structurally could not produce"}

    # --- CorrectlyUnmatched: is each DERIVED reason right? ----------------
    reason_of = truth.get("unsettled_reason", {})
    mapping = {
        "netted_out": "netted_out_by_full_refund",
        "rolled_forward": "rolled_forward_past_horizon",
        "not_yet_eligible": "not_yet_eligible_at_horizon",
        "dispute_held": "on_hold_dispute",
        "debit_deferred": "debit_deferred_past_horizon",
        "failed_at_gateway": "not_captured",
    }
    correct = mislabelled = unknown = 0
    for item in output.unmatched:
        for row_id in item.row_ids:
            actual = reason_of.get(row_id)
            if actual is None:
                unknown += 1
            elif mapping.get(item.reason.value) == actual:
                correct += 1
            else:
                mislabelled += 1
    measured["correctly_unmatched"] = {
        "reason_correct": correct, "reason_wrong": mislabelled,
        "row_settled_after_all": unknown,
        "note": "the REASON is scored, not the classification"}

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
