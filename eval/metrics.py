"""Scoring against the ground-truth key.

`eval/` is the ONLY package permitted to read `engine/ground_truth/`. Nothing
here is imported by `matching/`; the dependency runs one way, and
`tests/test_no_leakage.py` enforces it.

## The three definitions that decide what the numbers mean

**Match rate.** 37 of 240 rows are correctly unmatched -- netted out by a full
refund, rolled forward, held against a dispute, deferred, or failed at the
gateway. None of them CAN be matched to a bank credit and matching one would be
a false positive. They are excluded from the denominator and reported as their
own bucket, so:

    match rate = matched / (matched + genuinely unresolved)

Counting them as misses caps the score at 84.6% regardless of engine quality;
counting them as matches conflates "found its bank credit" with "explained why
it has none". Both distort. The third bucket is reported in full, per reason,
so the denominator is auditable rather than convenient.

**Precision and recall** are computed over DETERMINATE batches only. An
ambiguous batch has no single right answer to be precise about, and folding it
in either way is a measurement error rather than a result.

**Ambiguity handling** is a third outcome with its own metrics: were the
provably-unresolvable batches flagged, and was the true decomposition among the
candidates enumerated. Crediting a match when the truth is merely somewhere in
the candidate list would reward enumerating more candidates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

GROUND_TRUTH = (Path(__file__).resolve().parent.parent
                / "engine" / "ground_truth" / "ground_truth.json")


def load_truth(path: Path | None = None) -> dict:
    return json.loads((path or GROUND_TRUTH).read_text())


@dataclass
class MatchMetrics:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    scored_rows: int = 0
    excluded_ambiguous: int = 0

    @property
    def precision(self) -> float:
        placed = self.true_positives + self.false_positives
        return self.true_positives / placed if placed else 1.0

    @property
    def recall(self) -> float:
        actual = self.true_positives + self.false_negatives
        return self.true_positives / actual if actual else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class AmbiguityMetrics:
    planted: list[str] = field(default_factory=list)
    flagged: list[int] = field(default_factory=list)
    planted_detected: list[str] = field(default_factory=list)
    planted_missed: list[str] = field(default_factory=list)
    additional_flagged: list[str] = field(default_factory=list)
    truth_in_candidates: dict[str, bool] = field(default_factory=dict)
    truncated: list[int] = field(default_factory=list)

    @property
    def detection_recall(self) -> float:
        return len(self.planted_detected) / len(self.planted) if self.planted else 1.0

    @property
    def truth_always_enumerated(self) -> bool:
        return all(self.truth_in_candidates.values())


@dataclass
class Accounting:
    """Disjoint settlement-axis accounting: every row lands in exactly one bucket.

    The ERP and GST findings are a SEPARATE axis -- a payment can be correctly
    matched to its bank credit and still have no ERP order -- so they are not
    counted here. Mixing the two axes is how a row gets counted twice and how a
    match rate stops meaning anything.
    """

    #: truly settled (203 rows): what did the engine do with them
    placed_correctly: int = 0
    placed_incorrectly: int = 0
    declined_as_ambiguous: int = 0
    missed: int = 0
    #: truly unsettled (37 rows): what did the engine do with them
    correctly_left_unmatched: int = 0
    wrongly_placed: int = 0

    by_reason: dict[str, int] = field(default_factory=dict)
    total_rows: int = 0

    @property
    def truly_settled(self) -> int:
        return (self.placed_correctly + self.placed_incorrectly
                + self.declined_as_ambiguous + self.missed)

    @property
    def truly_unsettled(self) -> int:
        return self.correctly_left_unmatched + self.wrongly_placed

    @property
    def match_rate(self) -> float:
        """Correctly placed, over every row that HAS a bank credit to find.

        Rows that correctly have no bank credit are excluded from the
        denominator -- matching one would be a false positive, so counting it
        as a miss would penalise the engine for being right. They are reported
        in full below, by reason, so the exclusion is auditable.
        """
        return self.placed_correctly / self.truly_settled if self.truly_settled else 0.0

    @property
    def partitions(self) -> bool:
        return self.truly_settled + self.truly_unsettled == self.total_rows


def score(result, truth: dict | None = None):
    truth = truth or load_truth()
    bank_to_batch = result.bank_to_batch
    batch_by_id = {b["settlement_id"]: b for b in truth["batches"]}
    true_batch_of = {}
    for batch in truth["batches"]:
        for row_id in batch["credit_ids"] + batch["debit_ids"]:
            true_batch_of[row_id] = batch["settlement_id"]

    ambiguity = _score_ambiguity(result, truth, bank_to_batch, batch_by_id)
    ambiguous_bank_indexes = set(ambiguity.flagged)
    ambiguous_settlements = {
        bank_to_batch[i] for i in ambiguous_bank_indexes if i in bank_to_batch}

    match = MatchMetrics()
    for row_id, bank_index in sorted(result.stage3.assigned.items()):
        predicted = bank_to_batch.get(bank_index)
        actual = true_batch_of.get(row_id)
        if bank_index in ambiguous_bank_indexes or actual in ambiguous_settlements:
            match.excluded_ambiguous += 1
            continue
        match.scored_rows += 1
        if predicted == actual:
            match.true_positives += 1
        else:
            match.false_positives += 1

    placed = set(result.stage3.assigned)
    for row_id, settlement_id in sorted(true_batch_of.items()):
        if row_id in placed or settlement_id in ambiguous_settlements:
            continue
        if row_id in result.stage3.contested:
            continue
        match.false_negatives += 1

    accounting = Accounting(total_rows=len(result.dataset.rows))
    assigned = result.stage3.assigned
    contested = result.stage3.contested
    for row in result.dataset.rows:
        row_id = row["entity_id"]
        actual = true_batch_of.get(row_id)
        if actual:
            if row_id in assigned:
                predicted = bank_to_batch.get(assigned[row_id])
                if predicted == actual:
                    accounting.placed_correctly += 1
                else:
                    accounting.placed_incorrectly += 1
            elif row_id in contested:
                accounting.declined_as_ambiguous += 1
            else:
                accounting.missed += 1
        else:
            if row_id in assigned:
                accounting.wrongly_placed += 1
            else:
                accounting.correctly_left_unmatched += 1

    reasons = truth["unsettled_reason"]
    for row in result.dataset.rows:
        row_id = row["entity_id"]
        if row_id not in true_batch_of and row_id not in assigned:
            reason = reasons.get(row_id, "unknown")
            accounting.by_reason[reason] = accounting.by_reason.get(reason, 0) + 1

    return match, ambiguity, accounting


def _score_ambiguity(result, truth, bank_to_batch, batch_by_id) -> AmbiguityMetrics:
    from matching.model import Ambiguous

    metrics = AmbiguityMetrics()
    metrics.planted = sorted(b["settlement_id"] for b in truth["batches"]
                             if b["ambiguous"])
    for item in result.stage3.reconstructions:
        settlement_id = bank_to_batch.get(item.bank_index)
        resolution = item.resolution
        if isinstance(resolution, Ambiguous):
            metrics.flagged.append(item.bank_index)
            if resolution.truncated:
                metrics.truncated.append(item.bank_index)
            if settlement_id in metrics.planted:
                metrics.planted_detected.append(settlement_id)
            elif settlement_id:
                metrics.additional_flagged.append(settlement_id)

        if settlement_id and settlement_id in batch_by_id:
            batch = batch_by_id[settlement_id]
            true_rows = tuple(sorted(batch["credit_ids"] + batch["debit_ids"]))
            if isinstance(resolution, Ambiguous):
                found = any(candidate.row_ids == true_rows
                            for candidate in resolution.candidates)
            elif hasattr(resolution, "decomposition"):
                found = resolution.decomposition.row_ids == true_rows
            else:
                found = False
            metrics.truth_in_candidates[settlement_id] = found

    metrics.planted_missed = sorted(set(metrics.planted) - set(metrics.planted_detected))
    metrics.flagged.sort()
    return metrics


def false_positive_audit(result, truth: dict | None = None) -> dict:
    """The checks that matter more than the headline number.

    A matcher that pairs everything scores perfectly on recall and is worthless.
    These assert the engine did NOT match things that have no partner.
    """
    truth = truth or load_truth()
    erp_missing = set(truth["payments_missing_from_erp"])
    orphans = set(truth["erp_orphan_invoices"])

    matched_to_erp = set(result.stage1.row_to_erp) | set(result.stage3.erp_assignments)
    adjustments = {row["entity_id"] for row in result.dataset.rows
                   if row["type"] == "adjustment"}

    return {
        "erp_gap_payments_wrongly_matched": sorted(erp_missing & matched_to_erp),
        "orphan_invoices_wrongly_matched": sorted(
            orphans & set(result.stage1.row_to_erp.values())
            | orphans & set(result.stage3.erp_assignments.values())),
        "adjustments_given_a_counterparty": sorted(adjustments & matched_to_erp),
        #: proposed == made + refused. Reported so the stage can never render
        #: as a bare zero: a stage that appears to do nothing invites "why is
        #: this here", where one that reports its refusals has already answered.
        "hungarian_pairs_proposed": (len(result.stage3.erp_assignments)
                                     + len(result.stage3.erp_rejected)),
        "hungarian_assignments_made": len(result.stage3.erp_assignments),
        "hungarian_pairs_refused": len(result.stage3.erp_rejected),
        "fuzzy_pairs_refused": len(result.stage2.rejected),
    }
