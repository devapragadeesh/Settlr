"""Cold run of the FROZEN cascade against the held-out set.

Same solver (`81c04e0`), same metric definitions (`DECISIONS.md` sec 12), data
the engine has never seen. Writes `holdout/HOLDOUT_RESULTS.md`.

The cascade is not modified in response to anything this prints. If the
held-out numbers are worse, that is the finding and it is the headline.

    python3 eval/holdout_report.py [--runs 3]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.metrics import (  # noqa: E402
    candidate_set_sizes, false_positive_audit, load_truth, score)
from eval.report import fingerprint  # noqa: E402
from matching import run as run_cascade  # noqa: E402
from matching import stage4_exceptions  # noqa: E402
from matching.loaders import load  # noqa: E402
from matching.model import Ambiguous, Determinate, Unresolved  # noqa: E402
from matching.money import inr  # noqa: E402

HOLDOUT = ROOT / "holdout"


def kind_of(resolution) -> str:
    return {Determinate: "Determinate", Ambiguous: "Ambiguous",
            Unresolved: "Unresolved"}.get(type(resolution), type(resolution).__name__)


def analyse_reversals(result, truth) -> list[dict]:
    """What the frozen engine did with each planted reversal.

    Three bank lines per reversal -- the original credit A, the return debit,
    the re-settlement credit B -- plus where the affected rows actually landed.
    """
    by_index = {item.bank_index: item for item in result.stage3.reconstructions}
    bank_to_batch = result.bank_to_batch
    utr_to_index = {line.utr: line.index for line in result.dataset.bank if line.utr}
    # the return debit shares UTR-A with the original credit; separate on sign
    debit_index = {}
    credit_index = {}
    for line in result.dataset.bank:
        (debit_index if line.amount < 0 else credit_index)[line.utr] = line.index

    out = []
    for record in truth["planted_reversals"]:
        utr_a, utr_b = record["original_utr"], record["resettlement_utr"]
        a, d, b = (credit_index.get(utr_a), debit_index.get(utr_a),
                   credit_index.get(utr_b))
        rows = record["row_ids"]
        landed: dict[str, int] = {}
        for row_id in rows:
            if row_id in result.stage3.assigned:
                landed[row_id] = result.stage3.assigned[row_id]
        placement = {}
        for row_id, index in landed.items():
            placement.setdefault(index, []).append(row_id)

        out.append({
            "record": record,
            "credit_a_index": a, "debit_index": d, "credit_b_index": b,
            "credit_a": by_index.get(a), "debit": by_index.get(d),
            "credit_b": by_index.get(b),
            "credit_a_joined": a in bank_to_batch,
            "debit_joined": d in bank_to_batch,
            "credit_b_joined": b in bank_to_batch,
            "rows": rows,
            "placement": placement,
            "contested": [r for r in rows if r in result.stage3.contested],
            "unplaced": [r for r in rows
                         if r not in result.stage3.assigned
                         and r not in result.stage3.contested],
            "exception_rows": sorted(
                {e.entity_id for e in result.stage4.exceptions} & set(rows)),
        })
    return out


def score_predictions(result, truth, reversals, match, accounting,
                      p_match, p_acct) -> list[dict]:
    """Grade `HOLDOUT_SPEC.md` sec 3.2 against what actually happened.

    Computed from the run, never typed in, so the scorecard cannot flatter the
    prediction. Each row carries the falsification condition the spec named.
    """
    rev_rows = {row_id for item in reversals for row_id in item["rows"]}
    true_of = {}
    for batch in truth["batches"]:
        for row_id in batch["credit_ids"] + batch["debit_ids"]:
            true_of[row_id] = batch["settlement_id"]
    bank_to_batch = result.bank_to_batch
    misplaced = {row_id for row_id, index in result.stage3.assigned.items()
                 if true_of.get(row_id)
                 and bank_to_batch.get(index) != true_of.get(row_id)}

    debits_joined = [i for i in reversals if i["debit_joined"]]
    credit_a_joined = [i for i in reversals if i["credit_a_joined"]]
    a_determinate = [i for i in reversals
                     if i["credit_a"] and isinstance(i["credit_a"].resolution, Determinate)]
    placed_into_a = [i for i in reversals
                     if i["credit_a_index"] in i["placement"]]
    b_intact = []
    for item in reversals:
        recon = item["credit_b"]
        if recon and isinstance(recon.resolution, Determinate) and \
                sorted(recon.resolution.decomposition.row_ids) == sorted(item["rows"]):
            b_intact.append(item)
    debit_absorbed = [i for i in reversals
                      if i["debit"] and not isinstance(i["debit"].resolution, Unresolved)]

    return [
        {"id": "P1",
         "claim": "the reversal DEBIT is not joined by stage 1 or 2",
         "outcome": f"{len(debits_joined)} of {len(reversals)} debits joined",
         "held": not debits_joined},
        {"id": "P2",
         "claim": "the ORIGINAL credit A is not joined by stage 1 or 2",
         "outcome": f"{len(credit_a_joined)} of {len(reversals)} joined",
         "held": not credit_a_joined},
        {"id": "P3",
         "claim": "stage 3 places rows into credit A anyway -> placed_incorrectly, "
                  "NOT routed to exceptions (the brief predicted exceptions)",
         "outcome": (f"{len(a_determinate)}/{len(reversals)} credit-A lines resolved "
                     f"Determinate; {len(placed_into_a)}/{len(reversals)} took rows; "
                     f"{len(misplaced & rev_rows)} reversal rows scored "
                     f"placed_incorrectly"),
         "held": bool(a_determinate) and bool(placed_into_a) and bool(misplaced & rev_rows)},
        {"id": "P4",
         "claim": "credit B is damaged in turn -- its rows were already consumed",
         "outcome": (f"{len(reversals) - len(b_intact)} of {len(reversals)} "
                     "credit-B lines failed to reconstruct their true rows"),
         "held": not b_intact},
        {"id": "P5",
         "claim": "the reversal debit may be ABSORBED into a spurious decomposition",
         "outcome": (f"{len(debit_absorbed)} of {len(reversals)} debits absorbed; "
                     "the rest resolved Unresolved"),
         "held": bool(debit_absorbed)},
        {"id": "P6",
         "claim": "no balance-identity violation",
         "outcome": f"{len(result.balance_violations())} violations",
         "held": not result.balance_violations()},
        {"id": "P7",
         "claim": "match rate falls below the primary's and precision below 1.000",
         "outcome": (f"match rate {accounting.match_rate * 100:.2f}% vs "
                     f"{p_acct.match_rate * 100:.2f}%; precision "
                     f"{match.precision:.4f} vs {p_match.precision:.4f}"),
         "held": (accounting.match_rate < p_acct.match_rate
                  and match.precision < 1.0)},
    ]


def disaggregate(result, truth, reversals) -> dict:
    """Match rate over rows NOT touched by the unseen class.

    A DIAGNOSTIC, not the headline. The headline is the whole-set number in
    sec 1, because an engine does not get to exclude the cases it failed. This
    answers the separate and legitimate question of whether the drop is the
    new class or a general regression -- and it is only meaningful because
    every mis-placement turned out to be attributable.
    """
    rev_rows = {row_id for item in reversals for row_id in item["rows"]}
    true_of = {}
    for batch in truth["batches"]:
        for row_id in batch["credit_ids"] + batch["debit_ids"]:
            true_of[row_id] = batch["settlement_id"]
    bank_to_batch = result.bank_to_batch

    correct = wrong = declined = missed = 0
    for row_id, settlement_id in true_of.items():
        if row_id in rev_rows:
            continue
        if row_id in result.stage3.assigned:
            if bank_to_batch.get(result.stage3.assigned[row_id]) == settlement_id:
                correct += 1
            else:
                wrong += 1
        elif row_id in result.stage3.contested:
            declined += 1
        else:
            missed += 1
    total = correct + wrong + declined + missed
    return {"correct": correct, "wrong": wrong, "declined": declined,
            "missed": missed, "total": total,
            "match_rate": correct / total if total else 0.0,
            "reversal_rows": len(rev_rows),
            "misplaced_total": sum(
                1 for row_id, index in result.stage3.assigned.items()
                if true_of.get(row_id)
                and bank_to_batch.get(index) != true_of.get(row_id)),
            "misplaced_attributable": len({
                row_id for row_id, index in result.stage3.assigned.items()
                if true_of.get(row_id)
                and bank_to_batch.get(index) != true_of.get(row_id)} & rev_rows)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--llm", default="deterministic")
    args = parser.parse_args()

    holdout_data = load(HOLDOUT / "data")
    truth = load_truth(HOLDOUT / "ground_truth" / "ground_truth.json")

    digests, elapsed, result = [], [], None
    for _ in range(args.runs):
        began = time.perf_counter()
        result = run_cascade(dataset=holdout_data, llm=args.llm)
        elapsed.append(time.perf_counter() - began)
        digests.append(fingerprint(result))

    match, ambiguity, accounting = score(result, truth)
    audit = false_positive_audit(result, truth)
    candidates = candidate_set_sizes(result)
    reversals = analyse_reversals(result, truth)

    # the primary run, for the side-by-side. Same code path, frozen data.
    primary_result = run_cascade(llm=args.llm)
    p_match, p_amb, p_acct = score(primary_result, load_truth())
    p_candidates = candidate_set_sizes(primary_result)
    p_audit = false_positive_audit(primary_result, load_truth())

    out: list[str] = []
    w = out.append

    w("# HOLDOUT_RESULTS.md — cold run of the frozen cascade\n")
    w("Produced by `eval/holdout_report.py`. Solver frozen at `81c04e0` and")
    w("**not modified in response to anything below**. Metric definitions are")
    w("`DECISIONS.md` §12, unchanged, so the two columns are comparable.\n")
    w(f"Data: `holdout/`, seed `{truth['seed']}`, committed before generation.")
    w(f"Period {truth['period']['ledger_start']} .. "
      f"{truth['period']['ledger_end']}. "
      f"{len(result.dataset.rows)} rows, {len(result.dataset.bank)} bank lines "
      f"({sum(1 for b in result.dataset.bank if b.amount < 0)} of them debits, "
      "a shape the engine had never seen).\n")

    # ---- headline -------------------------------------------------------
    w("## 1. Headline\n")
    w("| metric | primary | **held-out** | delta |")
    w("|---|---:|---:|---:|")
    w(f"| match rate | {p_acct.match_rate * 100:.2f}% "
      f"({p_acct.placed_correctly}/{p_acct.truly_settled}) | "
      f"**{accounting.match_rate * 100:.2f}%** "
      f"({accounting.placed_correctly}/{accounting.truly_settled}) | "
      f"{(accounting.match_rate - p_acct.match_rate) * 100:+.2f} pp |")
    w(f"| precision (determinate batches) | {p_match.precision:.4f} | "
      f"**{match.precision:.4f}** | {match.precision - p_match.precision:+.4f} |")
    w(f"| recall (determinate batches) | {p_match.recall:.4f} | "
      f"**{match.recall:.4f}** | {match.recall - p_match.recall:+.4f} |")
    w(f"| rows placed in the wrong batch | {p_acct.placed_incorrectly} | "
      f"**{accounting.placed_incorrectly}** | "
      f"{accounting.placed_incorrectly - p_acct.placed_incorrectly:+d} |")
    w(f"| rows placed that should not settle | {p_acct.wrongly_placed} | "
      f"**{accounting.wrongly_placed}** | "
      f"{accounting.wrongly_placed - p_acct.wrongly_placed:+d} |")
    w(f"| balance-identity violations | {len(primary_result.balance_violations())} | "
      f"**{len(result.balance_violations())}** | "
      f"{len(result.balance_violations()) - len(primary_result.balance_violations()):+d} |")
    w(f"| ambiguous batches flagged | {len(p_amb.flagged)} | "
      f"**{len(ambiguity.flagged)}** | "
      f"{len(ambiguity.flagged) - len(p_amb.flagged):+d} |")
    w(f"| **mean candidate set size** | {p_candidates['mean']:.2f} | "
      f"**{candidates['mean']:.2f}** | "
      f"{candidates['mean'] - p_candidates['mean']:+.2f} |")
    w(f"| truth in candidates, every batch | {p_amb.truth_always_enumerated} | "
      f"**{ambiguity.truth_always_enumerated}** | |")
    w(f"| wall clock (mean of {args.runs}) | — | "
      f"**{sum(elapsed) / len(elapsed):.2f}s** | |")
    w("")

    # ---- accounting -----------------------------------------------------
    w("## 2. Row accounting — the same three buckets\n")
    w(f"Disjoint, and asserted to partition all {accounting.total_rows} rows "
      f"(`partitions == {accounting.partitions}`).\n")
    w("| bucket | primary | held-out |")
    w("|---|---:|---:|")
    w(f"| truly settled — placed correctly | {p_acct.placed_correctly} | "
      f"{accounting.placed_correctly} |")
    w(f"| truly settled — placed **incorrectly** | {p_acct.placed_incorrectly} | "
      f"{accounting.placed_incorrectly} |")
    w(f"| truly settled — declined, provably ambiguous | "
      f"{p_acct.declined_as_ambiguous} | {accounting.declined_as_ambiguous} |")
    w(f"| truly settled — missed | {p_acct.missed} | {accounting.missed} |")
    w(f"| truly unsettled — correctly left unmatched | "
      f"{p_acct.correctly_left_unmatched} | {accounting.correctly_left_unmatched} |")
    w(f"| truly unsettled — **wrongly placed** | {p_acct.wrongly_placed} | "
      f"{accounting.wrongly_placed} |")
    w("")
    w("### The excluded denominator, itemised\n")
    w("| true reason | primary | held-out |")
    w("|---|---:|---:|")
    for reason in sorted(set(accounting.by_reason) | set(p_acct.by_reason)):
        w(f"| `{reason}` | {p_acct.by_reason.get(reason, 0)} | "
          f"{accounting.by_reason.get(reason, 0)} |")
    w("")

    # ---- ambiguity ------------------------------------------------------
    w("## 3. Ambiguity handling\n")
    w(f"- planted, provably unresolvable batches: **{len(ambiguity.planted)}**")
    w(f"- detected: **{len(ambiguity.planted_detected)}** "
      f"(recall {ambiguity.detection_recall * 100:.0f}%)")
    w(f"- missed: **{len(ambiguity.planted_missed)}**"
      + (f" — `{'`, `'.join(ambiguity.planted_missed)}`" if ambiguity.planted_missed else ""))
    w(f"- additional batches flagged: **{len(ambiguity.additional_flagged)}**")
    w(f"- true decomposition present among the candidates on every batch: "
      f"**{ambiguity.truth_always_enumerated}**")
    w(f"- enumerations truncated at the cap: **{len(ambiguity.truncated)}**\n")
    w("### Mean candidate set size — reported unprompted\n")
    w("`truth_in_candidates` is gameable on its own: a solver returning all")
    w("2ⁿ subsets contains the truth every time and has decided nothing. The")
    w("candidate set size is what closes that loophole, so it is reported")
    w("beside the pool it was drawn from rather than left to be asked for.\n")
    w("| | primary | held-out |")
    w("|---|---:|---:|")
    w(f"| ambiguous bank lines | {p_candidates['count']} | {candidates['count']} |")
    w(f"| **mean candidate set size** | **{p_candidates['mean']:.2f}** | "
      f"**{candidates['mean']:.2f}** |")
    w(f"| min / max | {p_candidates['min']} / {p_candidates['max']} | "
      f"{candidates['min']} / {candidates['max']} |")
    w(f"| mean pool size those were drawn from | "
      f"{p_candidates['mean_pool_size']:.1f} rows | "
      f"{candidates['mean_pool_size']:.1f} rows |")
    w("")
    if candidates["count"]:
        w(f"The engine narrows a {candidates['mean_pool_size']:.0f}-row pool to "
          f"{candidates['mean']:.2f} candidates on average and then **refuses to "
          "choose between them**. That is the claim the number defends.\n")

    # ---- THE REVERSALS --------------------------------------------------
    w("## 4. The reversals — prediction vs outcome\n")
    w("The pre-registered prediction is `holdout/HOLDOUT_SPEC.md` §3, committed")
    w("before this script was ever run. Verify with `git log --reverse`.\n")

    scorecard = score_predictions(result, truth, reversals, match, accounting,
                                  p_match, p_acct)
    held = sum(1 for row in scorecard if row["held"])
    w(f"### 4.1 Scorecard — {held} of {len(scorecard)} predictions held\n")
    w("Computed from the run, not typed in.\n")
    w("| # | prediction | outcome | verdict |")
    w("|---|---|---|:-:|")
    for row in scorecard:
        w(f"| **{row['id']}** | {row['claim']} | {row['outcome']} | "
          f"{'HELD' if row['held'] else '**FALSIFIED**'} |")
    w("")
    for row in scorecard:
        if not row["held"]:
            w(f"**{row['id']} was wrong, and it is reported as wrong.** "
              f"Predicted: {row['claim']}. Actual: {row['outcome']}.\n")
    w("### 4.2 The headline finding of Task 2\n")
    w("**The brief's expectation was wrong, and so was part of mine.**\n")
    w("The brief expected the engine to route the affected rows to exceptions.")
    w("It does not. It places them into the *original* credit A with a closing")
    w("arithmetic proof and full confidence, and the ground truth says they")
    w("belong to the re-settlement B. That is a **confident wrong answer**, the")
    w("failure mode the phase brief named as the one to watch for, and it is")
    w("what actually happened on all three planted reversals.\n")
    w("The engine has **no representation for a bank credit that was later")
    w("revoked**. Stage 3 walks bank lines in date order and asks, of each, ")
    w("\"which pool rows net to this amount?\" At credit A's date the honest")
    w("answer is *those rows* — they genuinely did compose that credit, and the")
    w("credit genuinely posted. The engine is not hallucinating; it is answering")
    w("a question that has no memory of revocation in it. Detecting the reversal")
    w("requires relating a *later* debit back to an *earlier* credit, which is")
    w("state the cascade never carries.\n")
    w("A second-order cost, which is the part that would hurt in production: ")
    w("because credit A resolves `Determinate` and carries no attestation, "
      "`stage3_solver.run` takes the `elif` branch and **consumes** those rows.")
    w("Credit B then reconstructs from a pool its own rows are missing from — so")
    w("one reversal damages **two** bank lines, not one. On `bank[9]` that")
    w("surfaces as an ambiguity with 29 candidates where the true decomposition")
    w("is not even among them.\n")

    unresolved_lines = [i.bank_index for i in result.stage3.reconstructions
                        if isinstance(i.resolution, Unresolved)]
    debit_lines = [i["debit_index"] for i in reversals]
    w("**What the engine DID get right, and it is not nothing.** The reversal")
    w(f"debits themselves are not absorbed (P5 falsified): all "
      f"{len(debit_lines)} resolve `Unresolved` and reach the exception queue")
    w(f"as `genuinely_unresolved`, along with the damaged credit-B lines — "
      f"{len(unresolved_lines)} bank lines in total "
      f"(`{unresolved_lines}`), against 0 on the primary set. So the engine")
    w("does raise its hand about the **bank lines** it cannot explain. What it")
    w("does not do is revisit the **rows** it already placed with confidence.")
    w("The queue says \"I cannot explain these three debits\"; it does not say")
    w("\"...and therefore my earlier answer about credit A is void.\"\n")
    w("**The reversal is also expensive.** Held-out wall clock is "
      f"{sum(elapsed) / len(elapsed):.2f}s against the primary's ~1.4s, and")
    w("almost all of it is one line: the contaminated `bank[9]` takes "
      f"{max(result.stage3.reconstructions, key=lambda x: x.seconds).seconds:.2f}s")
    w("alone, enumerating 29 candidates over a 33-row pool because the rows that")
    w("would have closed it exactly were consumed by credit A. A pool polluted")
    w("by an unrecognised reversal is both slower and less decisive — the two")
    w("costs arrive together.\n")

    disagg = disaggregate(result, truth, reversals)
    w("### 4.3 How much of the drop is the unseen class\n")
    w("**A diagnostic, not the headline.** The headline stays 73.11% — an")
    w("engine does not get to exclude the cases it failed. This answers the")
    w("separate question of whether the drop is the new class or a general")
    w("regression, and it is only a fair question to ask because the")
    w("attribution turned out to be total:\n")
    w(f"- rows placed incorrectly: **{disagg['misplaced_total']}**")
    w(f"- of those, rows belonging to a reversed batch: "
      f"**{disagg['misplaced_attributable']}**")
    w(f"- rows placed incorrectly that are NOT reversal-related: "
      f"**{disagg['misplaced_total'] - disagg['misplaced_attributable']}**\n")
    w("| | primary | held-out, all rows | held-out, reversal rows excluded |")
    w("|---|---:|---:|---:|")
    w(f"| match rate | {p_acct.match_rate * 100:.2f}% | "
      f"**{accounting.match_rate * 100:.2f}%** | "
      f"{disagg['match_rate'] * 100:.2f}% |")
    w(f"| placed correctly | {p_acct.placed_correctly} | "
      f"{accounting.placed_correctly} | {disagg['correct']} |")
    w(f"| placed incorrectly | {p_acct.placed_incorrectly} | "
      f"{accounting.placed_incorrectly} | {disagg['wrong']} |")
    w(f"| declined as ambiguous | {p_acct.declined_as_ambiguous} | "
      f"{accounting.declined_as_ambiguous} | {disagg['declined']} |")
    w(f"| missed | {p_acct.missed} | {accounting.missed} | {disagg['missed']} |")
    w("")
    w("On the fifteen classes the engine HAS seen, held-out behaviour is")
    w(f"indistinguishable from primary: **{disagg['wrong']} rows placed")
    w(f"incorrectly**, **{disagg['missed']} missed**, and the same")
    w(f"{disagg['declined']} rows declined on proven ambiguity. The engine did")
    w("not degrade on unseen data drawn from classes it knows — it failed on")
    w("**one class it had never encountered**, and it failed by being")
    w("confident rather than by being silent.\n")
    w("The honest reading of both numbers together: the cascade generalises")
    w("across draws, and has a **specific, named, reproducible gap** that a")
    w("held-out set was the only way to find. Neither half of that sentence is")
    w("worth much without the other.\n")
    w("### 4.4 Per-reversal detail\n")
    for item in reversals:
        record = item["record"]
        w(f"### `{record['original_utr']}` → `{record['resettlement_utr']}` "
          f"({len(record['row_ids'])} rows, {inr(record['payout_paise'])})\n")
        w("| bank line | index | joined by stage 1/2 | stage 3 outcome |")
        w("|---|---:|:-:|---|")
        for label, key, idx in (
                ("credit A (original)", "credit_a", item["credit_a_index"]),
                ("DEBIT (the return)", "debit", item["debit_index"]),
                ("credit B (re-settlement)", "credit_b", item["credit_b_index"])):
            recon = item[key]
            outcome = kind_of(recon.resolution) if recon else "—"
            if recon and isinstance(recon.resolution, Ambiguous):
                outcome += f" ({len(recon.resolution.candidates)} candidates)"
            if recon and isinstance(recon.resolution, Determinate):
                outcome += (f" ({len(recon.resolution.decomposition.row_ids)} rows)")
            w(f"| {label} | {idx} | {item[key + '_joined']} | {outcome} |")
        w("")
        w(f"- rows placed by the engine: "
          + (", ".join(f"**{len(v)} → bank[{k}]**" for k, v in sorted(item['placement'].items()))
             or "none"))
        w(f"- rows declined as contested: {len(item['contested'])}")
        w(f"- rows left unplaced entirely: {len(item['unplaced'])}")
        w(f"- rows appearing in the exception queue: {len(item['exception_rows'])}")
        w("")

    # ---- exceptions -----------------------------------------------------
    w("## 5. Exception queue, itemised\n")
    by_type = result.stage4.by_type()
    p_by_type = primary_result.stage4.by_type()
    w("| type | primary | held-out | owner | actionable |")
    w("|---|---:|---:|---|:-:|")
    for kind in sorted(set(by_type) | set(p_by_type)):
        items = by_type.get(kind) or p_by_type.get(kind)
        actionable = "yes" if kind not in stage4_exceptions.NOT_A_PROBLEM else "no"
        w(f"| `{kind}` | {len(p_by_type.get(kind, []))} | "
          f"{len(by_type.get(kind, []))} | {items[0].owner} | {actionable} |")
    w(f"\n**{len(result.stage4.actionable)} actionable** of "
      f"{len(result.stage4.exceptions)} total "
      f"(primary: {len(primary_result.stage4.actionable)} of "
      f"{len(primary_result.stage4.exceptions)}).\n")

    # ---- false positives ------------------------------------------------
    w("## 6. False-positive audit\n")
    w("| check | primary | held-out |")
    w("|---|---:|---:|")
    for label, key in (
            ("ERP-gap payments wrongly given an invoice", "erp_gap_payments_wrongly_matched"),
            ("orphan ERP invoices wrongly given a payment", "orphan_invoices_wrongly_matched"),
            ("adjustment rows given a counterparty", "adjustments_given_a_counterparty")):
        w(f"| {label} | {len(p_audit[key])} | {len(audit[key])} |")
    for label, key in (("Hungarian pairs proposed", "hungarian_pairs_proposed"),
                       ("Hungarian pairs refused", "hungarian_pairs_refused"),
                       ("Hungarian assignments accepted", "hungarian_assignments_made"),
                       ("fuzzy pairs proposed then refused", "fuzzy_pairs_refused")):
        w(f"| {label} | {p_audit[key]} | {audit[key]} |")
    w("")

    # ---- runtime --------------------------------------------------------
    w("## 7. Runtime and determinism\n")
    w("| | seconds |")
    w("|---|---:|")
    for stage, seconds in result.timings.items():
        w(f"| {stage} | {seconds:.3f} |")
    w("")
    slowest = max(result.stage3.reconstructions, key=lambda x: x.seconds)
    w(f"Mean wall clock over {args.runs} runs: "
      f"**{sum(elapsed) / len(elapsed):.2f}s** "
      f"(min {min(elapsed):.2f}s, max {max(elapsed):.2f}s).")
    w(f"Slowest single bank line: `bank[{slowest.bank_index}]` at "
      f"{slowest.seconds:.2f}s over a {len(slowest.pool_ids)}-row pool.")
    over = [i.bank_index for i in result.stage3.reconstructions if i.over_time_budget]
    w(f"Bank lines over the 30s per-credit budget: **{len(over)}**"
      + (f" — {over}" if over else "") + ".\n")
    w(f"**Determinism:** {args.runs} consecutive runs on held-out data.\n")
    for index, dig in enumerate(digests):
        w(f"- run {index + 1}: `{dig[:16]}`")
    w(f"\nIdentical across all runs: **{len(set(digests)) == 1}**\n")

    (HOLDOUT / "HOLDOUT_RESULTS.md").write_text("\n".join(out) + "\n")

    # a machine-readable copy, so the narrative cannot drift from the run
    (HOLDOUT / "holdout_metrics.json").write_text(json.dumps({
        "seed": truth["seed"],
        "match_rate": accounting.match_rate,
        "precision": match.precision, "recall": match.recall,
        "placed_correctly": accounting.placed_correctly,
        "placed_incorrectly": accounting.placed_incorrectly,
        "declined_as_ambiguous": accounting.declined_as_ambiguous,
        "missed": accounting.missed,
        "correctly_left_unmatched": accounting.correctly_left_unmatched,
        "wrongly_placed": accounting.wrongly_placed,
        "truly_settled": accounting.truly_settled,
        "balance_violations": result.balance_violations(),
        "candidates": candidates,
        "ambiguity_flagged": len(ambiguity.flagged),
        "ambiguity_planted": len(ambiguity.planted),
        "ambiguity_detected": len(ambiguity.planted_detected),
        "truth_always_enumerated": ambiguity.truth_always_enumerated,
        "mean_seconds": sum(elapsed) / len(elapsed),
        "deterministic": len(set(digests)) == 1,
        "predictions": [{"id": row["id"], "held": row["held"],
                         "outcome": row["outcome"]} for row in scorecard],
        "disaggregated": disagg,
        "primary": {"match_rate": p_acct.match_rate,
                    "precision": p_match.precision, "recall": p_match.recall,
                    "candidates": p_candidates},
    }, indent=1, default=str) + "\n")

    print(f"held-out: match rate {accounting.match_rate * 100:.2f}%  "
          f"precision {match.precision:.4f}  recall {match.recall:.4f}")
    print(f"primary : match rate {p_acct.match_rate * 100:.2f}%  "
          f"precision {p_match.precision:.4f}  recall {p_match.recall:.4f}")
    print(f"placed_incorrectly {accounting.placed_incorrectly}, "
          f"wrongly_placed {accounting.wrongly_placed}, "
          f"balance violations {len(result.balance_violations())}")
    print(f"mean candidate set size {candidates['mean']:.2f}  "
          f"deterministic={len(set(digests)) == 1}  "
          f"{sum(elapsed) / len(elapsed):.2f}s/run")


if __name__ == "__main__":
    main()
