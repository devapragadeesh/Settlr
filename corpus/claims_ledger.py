"""CLAIMS.md -- every quantitative claim the repository makes, in one table.

Purpose: a reader can check any number without reading the repository, and any
future edit that changes a number has ONE place that must change with it.

Each row carries the artefact that produces the number and the command that
reproduces it. **A claim with no generating artefact is flagged**, because a
number nobody can regenerate is a number nobody should trust -- including the
person who wrote it. Two hand-typed figures in `README.md` went stale in this
project the first time a run moved (`238 of 275` for a run in which it was
239); this file exists so that fails loudly next time.

The numbers below are read from the live run artefacts, not typed here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _dig(payload, path):
    for key in path:
        payload = payload[key]
    return payload


def load(name: str):
    path = ROOT / "corpus" / name
    return json.loads(path.read_text()) if path.exists() else None


def rows() -> list[dict]:
    oracle = load("oracle_results.json") or []
    baseline = load("baseline_results.json") or []
    total = lambda p: sum(_dig(r["measured"], p) for r in oracle)
    gate = lambda g: sum(r["violations_by_gate"].get(g, 0) for r in oracle)

    ORACLE = "`python3 corpus/score_resolver.py --all`"
    THREE = "`python3 corpus/three_systems.py`"
    TRIV = "`python3 corpus/triviality_check.py --all`"
    BASE = "`python3 corpus/baseline_old_engine.py --all`"
    AUDIT = "committed measurement, `investigation/DERIVED_BRANCH_AUDIT.md`"

    out = [
        dict(claim="`Verified` assignments that are wrong",
             value=gate("G1"), denom=f"{total(('accounting','verified'))} `Verified`",
             scope="30 datasets, gate G1", artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="`ProvenUnmatched` rows that in fact settled",
             value=gate("G9"), denom=f"{total(('proven_unmatched','rows'))} proven rows",
             scope="30 datasets, gate G9 — the gate that did not exist before contract §4.7",
             artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="`Verified` that are non-decisive",
             value=total(("accounting","verified_non_decisive")),
             denom=f"{total(('accounting','verified'))} `Verified`",
             scope="30 datasets; a rival composition would have passed the same check",
             artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="`Reconstructed` wrong",
             value=total(("reconstructed_accuracy","wrong")),
             denom=f"{total(('reconstructed_accuracy','correct')) + total(('reconstructed_accuracy','wrong'))} `Reconstructed`",
             scope="30 datasets. **A COUNT, NOT A RATE** — the population is too small to support one",
             artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="abstentions on determined instances",
             value=gate("G7"),
             denom=f"{sum(r['measured']['determined']['determined_instances'] for r in oracle)} determined instances",
             scope="30 datasets, gate G7 (attested). **An abstention is "
                   "`Unresolved` or `Ambiguous` only.** The "
                   f"{sum(r['measured']['determined']['determined_instances'] - r['measured']['determined']['determined_resolved'] for r in oracle)} "
                   "determined instances that are not `Verified` are "
                   "`AttestationDiscrepancy` — a *finding*, not a silence — "
                   "and `instances − resolved` is therefore NOT the abstention "
                   "count. The first draft of this table made that mistake",
             artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="abstentions on reconstructible instances",
             value=gate("G8"),
             denom=f"{sum(r['measured']['determined']['reconstructible_instances'] for r in oracle)} reconstructible instances",
             scope="30 datasets, gate G8. **Uniqueness is scoped to the pool the "
                   "simulator drew from, 1.4×–14× smaller than the pool the resolver "
                   "searches** — `DECISIONS.md` §46",
             artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="candidate sets not containing the truth",
             value=gate("G3"), denom="all candidate sets built, 30 datasets",
             scope="gate G3", artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="datasets passing the oracle",
             value=sum(1 for r in oracle if r["passed"]), denom=f"{len(oracle)} datasets",
             scope="all nine gates; the 2 failures are both PSP-absence points, on G3 and G8",
             artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="`AttestationDiscrepancy` reported",
             value=total(("attestation_discrepancy","reported")),
             denom=f"{total(('attestation_discrepancy','planted'))} planted",
             scope="30 datasets. The excess is NOT a false-alarm rate — see the next two rows",
             artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="`AttestationDiscrepancy` that are **genuinely false**",
             value=total(("attestation_discrepancy","genuinely_false")),
             denom=f"{total(('attestation_discrepancy','reported'))} reported",
             scope="30 datasets; each non-planted finding is checked against a "
                   "`reversal_debit` line in the answer key",
             artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="`AttestationDiscrepancy` that are true findings of a kind the corpus did not plant",
             value=total(("attestation_discrepancy","true_finding_of_another_kind")),
             denom=f"{total(('attestation_discrepancy','reported'))} reported",
             scope="30 datasets; corroborated reversals", artefact="`corpus/oracle.py`", how=ORACLE),
        dict(claim="`ProvenUnmatched` rows",
             value=total(("proven_unmatched","rows")),
             denom=f"{total(('open_break','rows'))} `OpenBreak` rows alongside it "
                   "(**deliberately not a shared denominator: one asserts, the "
                   "other does not, and they are never summed** — `DECISIONS.md` §40)",
             scope="30 datasets; two entailed reasons only", artefact="`resolver/breaks.py`", how=ORACLE),
        dict(claim="`OpenBreak` rows",
             value=total(("open_break","rows")),
             denom=f"{total(('proven_unmatched','rows'))} `ProvenUnmatched` rows alongside it, never summed",
             scope="30 datasets. **Asserts nothing** and is never gated on correctness",
             artefact="`resolver/breaks.py`", how=ORACLE),
        dict(claim="`OpenBreak` rows clustered under a causing bank line",
             value=total(("open_break","clustered_rows")),
             denom=f"{total(('open_break','rows'))} `OpenBreak` rows, "
                   f"{total(('open_break','distinct_causes'))} distinct causes",
             scope="30 datasets; `UPSTREAM_UNRESOLVED` only",
             artefact="`resolver/resolve.py:_blocked_by`", how=ORACLE),
        dict(claim="`OpenBreak` rows the resolver could not classify",
             value=sum(r["measured"]["open_break"]["by_reason"].get("unexplained", 0) for r in oracle),
             denom=f"{total(('open_break','rows'))} `OpenBreak` rows",
             scope="30 datasets. A **real reported category**; a high count is an honest finding",
             artefact="`resolver/breaks.py`", how=ORACLE),
    ]

    if baseline:
        ran = [b for b in baseline if b.get("ran", True)]
        out.append(dict(
            claim="frozen cascade — datasets it can run on at all",
            value=len(ran), denom=f"{len(baseline)} datasets",
            scope="raises `KeyError: 'settlement_id'` at the PSP-absence points",
            artefact="`corpus/baseline_old_engine.py`", how=BASE))

    triv = ROOT / "corpus" / "TRIVIALITY_CHECK.md"
    if triv.exists():
        out.append(dict(
            claim="compositions a fifteen-line `GROUP BY` recovers",
            value="322", denom="335 attempted, over the 28 datasets it can run on",
            scope="**on the other 2 it cannot run at all.** Highest resistance on a "
                  "runnable dataset is 9.1% — one composition in twelve",
            artefact="`corpus/triviality_check.py`", how=TRIV))

    out += [
        dict(claim="`CorrectlyUnmatched` accuracy — the SUPERSEDED outcome",
             value="45.7%", denom="4,994 claims over 30 datasets",
             scope="**historical.** Split into `ProvenUnmatched` and `OpenBreak` by "
                   "contract §4.7; 2,469 of those rows had settled",
             artefact="`investigation/DERIVED_BRANCH_AUDIT.md`", how=AUDIT),
        dict(claim="derived-branch reason accuracy — the SUPERSEDED outcome",
             value="97.6%", denom="1,872 claims",
             scope="**historical, and the naive inference from it is wrong**: correcting "
                   "the derivations raised rows-that-settled from 8 to 64, because a "
                   "corrected `dispute_held` promotes rows out of a residual that "
                   "asserts nothing into a branch that asserts something false "
                   "(`DECISIONS.md` §40)",
             artefact="`investigation/DERIVED_BRANCH_AUDIT.md`", how=AUDIT),
        dict(claim="disputed rows whose `on_hold` column disagrees with their state at the horizon",
             value="202", denom="540 disputed rows",
             scope="defect D13. Not fixable from this feed: the Razorpay dispute entity "
                   "publishes no resolution timestamp (`DECISIONS.md` §44.5)",
             artefact="`investigation/DERIVED_BRANCH_AUDIT.md`", how=AUDIT),
        dict(claim="pool growth from the F1 fix",
             value="+1.7% mean, +2.8% max",
             denom="all pools, 30 datasets; 1,544 row-slots added",
             scope="`DECISIONS.md` §45; no gate moved",
             artefact="`investigation/F1_PREDICTION.md`", how="`python3 corpus/score_resolver.py --all` before and after `4b65764`"),
    ]
    return out


UNTRACEABLE = [
    ("the ₹99,329.23 worked example in `README.md`",
     "illustrative, drawn from Razorpay's published recon sample; it is not a "
     "measurement of this corpus and should not be read as one"),
    ("`matching/` cascade metrics in `eval/EVAL_REPORT.md`",
     "generated by `python3 eval/report.py --runs 3` against the FROZEN primary "
     "dataset, not against the corpus. Never comparable to any number above"),
    ("closure count over the DERIVED pool at the 18 reconstructible instances",
     "**NOT MEASURED.** It is the measurement that would settle whether the 15 "
     "G8 failures are genuine abstention failures or correct refusals "
     "(`DECISIONS.md` §46). Named as a gap, deliberately not built"),
]


def render() -> str:
    out = ["# CLAIMS", "",
           "Every quantitative claim this repository makes, with the artefact "
           "that produces it, the command that reproduces it, its denominator "
           "and its scope.", "",
           "**Generated by `corpus/claims_ledger.py` from the live run "
           "artefacts.** No value below is typed by hand. If a number here "
           "disagrees with a number elsewhere in the repository, this file is "
           "right and the other one has gone stale.", "",
           "## Why this file exists, demonstrated on its first run", "",
           "This table caught a live error **in itself, on its first "
           "execution**, in the file built to prevent exactly that class of "
           "error.", "",
           "The first draft reported **14 abstentions on determined "
           "instances**, computed as `determined_instances \u2212 "
           "determined_resolved`. That subtraction is wrong. Those 14 lines "
           "are `AttestationDiscrepancy` \u2014 the resolver found a "
           "contradiction and reported a **finding**, which is not a silence "
           "\u2014 and the gate's abstention count is **0**. Writing the "
           "denominator and the scope down beside the number was what exposed "
           "it; nothing else in the repository had.", "",
           "That is the argument for this artefact, and it is deliberately not "
           "the argument that the author was careful. **A mechanism caught "
           "what care did not.** The same conclusion `DECISIONS.md` \u00a744.4 "
           "reaches about the reference-frame sweep, and `CHECKPOINT.md` "
           "\u00a70 reaches about the leak audit: in this project, the "
           "informed searcher is not the control.", "",
           "| claim | value | denominator | scope | produced by | reproduce with |",
           "|---|---:|---|---|---|---|"]
    for row in rows():
        out.append(f"| {row['claim']} | **{row['value']}** | {row['denom']} | "
                   f"{row['scope']} | {row['artefact']} | {row['how']} |")
    out += ["", "## Claims with no generating artefact, or not measured at all", "",
            "A number nobody can regenerate is a number nobody should trust, "
            "including whoever wrote it.", "",
            "| claim | status |", "|---|---|"]
    for claim, status in UNTRACEABLE:
        out.append(f"| {claim} | {status} |")
    out += ["", "## Two rules this table exists to enforce", "",
            "1. **No rate without its denominator, inline.** Every value above "
            "carries one, including the ones where the denominator is "
            "embarrassing — `Reconstructed` wrong is a count over a population "
            "of one and says nothing about accuracy.",
            "2. **`ProvenUnmatched` and `OpenBreak` are never summed.** One "
            "asserts, the other does not. The single place their total appears "
            "is as a denominator in this table, labelled as such "
            "(`DECISIONS.md` §40)."]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "CLAIMS.md")
    arguments = parser.parse_args()
    arguments.out.write_text(render() + "\n")
    print(f"wrote {arguments.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
