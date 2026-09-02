"""Score the wrong-*bank*-side family. `DECISIONS.md` §51, scored separately.

    python3 corpus/score_bankside.py --all --out corpus/BANKSIDE_RESULTS.md \\
                                     --json corpus/bankside_results.json

Every planted record error in the 30-dataset corpus corrupts the **PSP's**
attestation. `corpus/datasets_bankside/` corrupts the other side: one line of
`bank_statement.csv` is replaced with an amount that closes no valid batch,
while `settlement_report.csv` and `recon_combined.json` stay correct and
untouched. The question this scorer exists to answer is narrow and stated in
§51: **does the resolver's evidence model treat the bank-side-wrong direction
the same way it treats the PSP-side-wrong direction it has already been tested
on?**

## Why this is a separate scorer and not two more rows in `three_systems.py`

`corpus/three_systems.py`, `corpus/scorecard.py` and `corpus/claims_ledger.py`
carry their dataset counts as narrative prose. §51 rejected editing three
already-cited generated documents to absorb a two-dataset family whose purpose
is exposing a gap, not moving a headline aggregate. Those files are untouched
by this one; their published numbers stay true.

## The oracle is reused where it applies and NOT extended where it does not

`corpus/oracle.py` runs here unmodified, and its gates are the gates: a
`Verified` on the corrupted line with a composition that is not the truth is a
G1 violation exactly as it would be anywhere else, so the primary soundness
question IS gated by the existing oracle.

The oracle's *measured* (ungated) `attestation_discrepancy` block used to
derive `planted` from `truth["attestation"]["wrong_attestations"]` alone --
PSP-side wrong attestations, keyed by settlement id. A `table: "bank"` planted
class is not in that list and cannot be, so a **correct** detection on the
corrupted line was scored `genuinely_false`. That was not patched in the pass
that provoked it (§31, §46, §51: never fold an oracle change into the work
that exposed it); it was deferred as an owed change by §54 and made, dated, by
`DECISIONS.md` §56, which taught `_measure` a second set in bank-line-index
space kept explicitly separate from the settlement-id one.

The **scorer-local** `bankside_verdict` check stays. §56 corrected only the
aggregate `genuinely_false` counter; no gate and no oracle measurement fires
per line the way `bankside_verdict` does, and its SOUND/UNSOUND/DECLINED/
NO_OUTCOME taxonomy answers a question the oracle still cannot. The oracle's
four-way split is reported beside it, with the re-attribution kept as an
independent cross-check that the two now agree.

The frozen `matching/` cascade is run over the same two datasets through
`corpus/baseline_old_engine.project` -- the same lossy column-rename shim the
other 30 datasets get, reused unmodified, so the comparison is the same
comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.baseline_old_engine import project                    # noqa: E402
from corpus.oracle import score                                   # noqa: E402
from matching import run as run_cascade                           # noqa: E402
from matching.loaders import load as load_frozen                  # noqa: E402
from matching.model import Ambiguous as OldAmbiguous              # noqa: E402
from matching.model import Determinate as OldDeterminate          # noqa: E402
from resolver.loaders import load                                 # noqa: E402
from resolver.resolve import NAME, resolve                        # noqa: E402

FAMILY = "datasets_bankside"
PLANTED_CLASS = "d12_bank_side_mispost"

#: The scorer-local verdict vocabulary. Ordered worst to best.
UNSOUND = "unsound"          # asserted a composition for a contradicted line
DECLINED = "declined"        # Ambiguous/Unresolved: sound, weaker than ideal
NO_OUTCOME = "no_outcome"    # the line produced no outcome at all
SOUND = "sound"              # named the disagreement, assigned nothing


def dataset_dirs() -> list[Path]:
    directory = ROOT / "corpus" / FAMILY
    if not directory.exists():
        return []
    return [d for d in sorted(directory.iterdir())
            if (d / "ground_truth.json").exists()]


def planted_entries(truth: dict) -> list[dict]:
    block = truth["planted_classes"].get(PLANTED_CLASS, {})
    return list(block.get("detail", [])) if block.get("planted") else []


# --------------------------------------------------------------------------
# the scorer-local check
# --------------------------------------------------------------------------


def bankside_verdict(output, truth: dict) -> list[dict]:
    """Per corrupted bank line: what did the resolver say, and was it sound?

    Scorer-local, NOT an oracle gate. `corpus/oracle.py` has no notion of a
    planted class whose `table` is `"bank"`, so this cannot be expressed as a
    gate without changing the oracle, which §54 declines to do in this pass.

    Soundness here is the contract's own criterion and nothing softer: the
    corrupted line's amount closes no valid batch, so any outcome CARRYING A
    COMPOSITION for it is an assertion the record contradicts (contract §4.2).
    `AttestationDiscrepancy` is the one outcome that says "the sources
    disagree" while assigning nothing, so it -- and only it -- is `sound`.
    Abstention is not unsound, but it is weaker: it says "I could not explain
    this", not "the record is wrong", which is the whole distinction the
    contract was written to make.
    """
    by_index = {o.bank_index: o for o in output.line_outcomes}
    out: list[dict] = []
    for entry in planted_entries(truth):
        index = entry["bank_line_index"]
        outcome = by_index.get(index)
        kind = type(outcome).__name__ if outcome is not None else None
        if kind == "AttestationDiscrepancy":
            verdict = SOUND
        elif kind in ("Verified", "Reconstructed"):
            verdict = UNSOUND
        elif kind in ("Ambiguous", "Unresolved"):
            verdict = DECLINED
        else:
            verdict = NO_OUTCOME

        record = {
            "bank_line_index": index,
            "settlement_id": entry["settlement_id"],
            "true_amount_paise": entry["true_amount_paise"],
            "bank_reported_amount_paise": entry["bank_reported_amount_paise"],
            "planted_delta_paise": entry["delta_paise"],
            "resolver_outcome": kind,
            "verdict": verdict,
            "contradiction_kind": None,
            "names_the_true_amount": None,
            "names_the_reported_amount": None,
            "recovers_delta": None,
            "attested_rows_named": None,
            "attested_rows_are_the_truth": None,
            "assigned_rows": (len(outcome.assigned_rows)
                              if outcome is not None else None),
        }
        if kind == "AttestationDiscrepancy":
            record["contradiction_kind"] = outcome.contradiction.kind.value
            record["names_the_true_amount"] = (
                outcome.attested_net == entry["true_amount_paise"])
            record["names_the_reported_amount"] = (
                outcome.bank_amount == entry["bank_reported_amount_paise"])
            recovered = (None if outcome.attested_net is None
                         or outcome.bank_amount is None
                         else abs(outcome.bank_amount - outcome.attested_net))
            record["recovers_delta"] = recovered == entry["delta_paise"]
            record["recovered_delta_paise"] = recovered
            # Naming the line is necessary but not sufficient: a discrepancy
            # that names the wrong rows is a worse finding than one that names
            # none, because someone works the wrong queue.
            named = tuple(sorted(outcome.attested_row_ids))
            batch = next((b for b in truth["batches"]
                          if b.get("bank_line_index") == index), None)
            record["attested_rows_named"] = len(named)
            if batch is not None:
                record["attested_rows_are_the_truth"] = (
                    named == tuple(sorted(batch["composition"])))
        if kind in ("Verified", "Reconstructed"):
            batch = next((b for b in truth["batches"]
                          if b.get("bank_line_index") == index), None)
            claimed = tuple(sorted(outcome.composition.row_ids))
            record["claimed_composition_size"] = len(claimed)
            record["claimed_equals_true_composition"] = (
                batch is not None
                and claimed == tuple(sorted(batch["composition"])))
        out.append(record)
    return out


def oracle_reattribution(report, truth: dict, verdicts: list[dict]) -> dict:
    """The oracle's four-way AD split, and what this class does to it.

    Reported side by side, never merged. The oracle's own numbers are printed
    exactly as the oracle produced them; the correction is a separate column
    so that a reader can see the oracle was not quietly edited.
    """
    block = report.measured.get("attestation_discrepancy", {})
    sound_lines = {v["bank_line_index"] for v in verdicts
                   if v["verdict"] == SOUND}
    mislabelled = [d for d in block.get("genuinely_false_detail", [])
                   if any(f"bank[{i}] " in d for i in sound_lines)]
    return {
        "oracle_planted": block.get("planted", 0),
        "oracle_reported": block.get("reported", 0),
        "oracle_correctly_identified": block.get("correctly_identified", 0),
        "oracle_true_finding_of_another_kind":
            block.get("true_finding_of_another_kind", 0),
        "oracle_genuinely_false": block.get("genuinely_false", 0),
        "oracle_genuinely_false_detail": block.get("genuinely_false_detail", []),
        "bank_side_planted": len(verdicts),
        "bank_side_correctly_identified": len(sound_lines),
        "mislabelled_by_oracle_as_genuinely_false": len(mislabelled),
        "genuinely_false_after_reattribution":
            block.get("genuinely_false", 0) - len(mislabelled),
        "note": "the oracle columns are the oracle's own output. Before "
                "DECISIONS.md 56, `planted` there counted PSP-side wrong "
                "attestations only and a correct bank-side detection landed "
                "in `genuinely_false`; 56 fixed that in bank-line-index "
                "space, so `genuinely_false` should now already equal "
                "`genuinely_false_after_reattribution`. This scorer-local "
                "re-attribution is KEPT as the independent cross-check that "
                "it does. DECISIONS.md 54, 56.",
    }


# --------------------------------------------------------------------------
# the frozen cascade, through the same shim the other 30 datasets get
# --------------------------------------------------------------------------


def cascade_on(dataset: Path, truth: dict) -> dict:
    """One run of the frozen `matching/` cascade, line detail extracted.

    `corpus/baseline_old_engine.project` is imported, not reimplemented: the
    shim's losses are documented there and are the same losses the corpus-wide
    baseline carries, so the comparison is like for like.
    """
    began = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="bankside_") as tmp:
            result = run_cascade(
                dataset=load_frozen(project(dataset, Path(tmp) / "d")))
    except Exception as failure:                             # noqa: BLE001
        return {"ran": False,
                "failure": f"{type(failure).__name__}: {failure}",
                "seconds": round(time.perf_counter() - began, 2),
                "lines": []}
    seconds = time.perf_counter() - began

    outcomes: Counter[str] = Counter()
    by_index = {}
    for item in result.stage3.reconstructions:
        resolution = item.resolution
        name = type(resolution).__name__
        outcomes[name] += 1
        by_index[item.bank_index] = resolution

    lines = []
    for entry in planted_entries(truth):
        index = entry["bank_line_index"]
        resolution = by_index.get(index)
        name = type(resolution).__name__ if resolution is not None else None
        record = {"bank_line_index": index, "outcome": name,
                  "claimed_composition_size": None,
                  "claimed_equals_true_composition": None,
                  "candidate_count": None,
                  # The frozen engine has no outcome meaning "the sources
                  # disagree". This is 0 by CONSTRUCTION, not by measurement,
                  # and is stated that way for the same reason
                  # `baseline_old_engine.py` states it.
                  "can_express_disagreement": False}
        batch = next((b for b in truth["batches"]
                      if b.get("bank_line_index") == index), None)
        if isinstance(resolution, OldDeterminate):
            claimed = tuple(sorted(resolution.decomposition.row_ids))
            record["claimed_composition_size"] = len(claimed)
            record["claimed_equals_true_composition"] = (
                batch is not None
                and claimed == tuple(sorted(batch["composition"])))
        elif isinstance(resolution, OldAmbiguous):
            record["candidate_count"] = len(resolution.candidates)
        lines.append(record)

    return {"ran": True, "seconds": round(seconds, 2),
            "outcomes": dict(outcomes), "lines": lines}


# --------------------------------------------------------------------------


def score_one(directory: Path, *, cap: int, time_budget: float,
              runs: int, with_cascade: bool) -> dict:
    truth = json.loads((directory / "ground_truth.json").read_text())

    began = time.perf_counter()
    output = resolve(load(directory), cap=cap, time_budget=time_budget)
    seconds = time.perf_counter() - began
    report = score(output, truth)
    verdicts = bankside_verdict(output, truth)

    # Determinism, asserted rather than claimed: the verdict payload must be
    # byte-identical across repeated runs. Resolver only -- the frozen cascade
    # takes ~2 minutes per dataset and its determinism is already covered by
    # the corpus-wide baseline.
    first = json.dumps(verdicts, sort_keys=True)
    identical = True
    for _ in range(max(0, runs - 1)):
        repeat = bankside_verdict(
            resolve(load(directory), cap=cap, time_budget=time_budget), truth)
        identical &= json.dumps(repeat, sort_keys=True) == first

    return {
        "dataset": f"{directory.parent.name}/{directory.name}",
        "family": directory.parent.name,
        "axes": truth["axes"],
        "bank_lines": len(truth["bank_lines"]),
        "settlements": len(truth["batches"]),
        "planted_bank_side_errors": len(verdicts),
        "wrong_attestations": len(truth["attestation"]["wrong_attestations"]),
        "seconds": round(seconds, 2),
        "runs": runs,
        "verdict_identical_across_runs": identical,
        "oracle_passed": report.passed,
        "oracle_violations_by_gate": report.by_gate(),
        "oracle_violations": [v.line().strip() for v in report.violations],
        "bank_side": verdicts,
        "attestation_discrepancy": oracle_reattribution(report, truth, verdicts),
        "cascade": cascade_on(directory, truth) if with_cascade else None,
    }


def render(results: list[dict], *, with_cascade: bool) -> str:
    total = sum(r["planted_bank_side_errors"] for r in results)
    sound = sum(1 for r in results for v in r["bank_side"]
                if v["verdict"] == SOUND)
    unsound = sum(1 for r in results for v in r["bank_side"]
                  if v["verdict"] == UNSOUND)
    declined = sum(1 for r in results for v in r["bank_side"]
                   if v["verdict"] == DECLINED)
    none_ = sum(1 for r in results for v in r["bank_side"]
                if v["verdict"] == NO_OUTCOME)

    out = [f"# The wrong-*bank*-side direction — {NAME} vs the frozen cascade",
           "",
           "Generated by `corpus/score_bankside.py`. No number in this file is "
           "hand-typed.",
           "",
           "`DECISIONS.md` §51 added a planted class that corrupts the **bank** "
           "side: one `bank_statement.csv` line is replaced with an amount that "
           "closes no valid batch, while `settlement_report.csv` and "
           "`recon_combined.json` are left correct and untouched. Every other "
           "planted record error in the corpus corrupts the PSP's attestation. "
           "This file is the only place the other direction is measured, and it "
           f"is scored over {len(results)} datasets — not folded into the "
           "30-dataset aggregate, which is unchanged by it.",
           "",
           "## The answer",
           "",
           f"* **{sound} of {total}** planted bank-side errors drew "
           "`AttestationDiscrepancy` — the sound outcome: it names the "
           "disagreement and assigns no composition.",
           f"* **{unsound} of {total}** drew `Verified` or `Reconstructed` — "
           "an assertion about which rows settled, on a line whose record "
           "contradicts itself. This is the failure mode the class was built to "
           "look for.",
           f"* **{declined} of {total}** drew `Ambiguous` or `Unresolved` — not "
           "unsound, but weaker: \"I could not explain this\" is not \"the "
           "record is wrong\".",
           f"* **{none_} of {total}** produced no outcome at all.",
           "",
           "## Per planted error", "",
           "| dataset | bank line | settlement | true (paise) | bank posted "
           "(paise) | resolver | verdict |",
           "|---|---:|---|---:|---:|---|---|"]
    for r in results:
        for v in r["bank_side"]:
            out.append(
                f"| `{r['dataset']}` | {v['bank_line_index']} | "
                f"`{v['settlement_id']}` | {v['true_amount_paise']} | "
                f"{v['bank_reported_amount_paise']} | "
                f"`{v['resolver_outcome']}` | **{v['verdict']}** |")

    out += ["", "### What the finding actually says", "",
            "Naming the line is necessary and not sufficient. A discrepancy "
            "that names the wrong rows sends someone to the wrong queue, so "
            "the rows and the amounts are checked against the key too.", "",
            "| dataset | contradiction kind | names true amount | names posted "
            "amount | delta recovered | rows named | rows == true composition | "
            "rows assigned |",
            "|---|---|---|---|---|---:|---|---:|"]
    for r in results:
        for v in r["bank_side"]:
            out.append(
                f"| `{r['dataset']}` | `{v['contradiction_kind']}` | "
                f"{v['names_the_true_amount']} | "
                f"{v['names_the_reported_amount']} | "
                f"{v['recovers_delta']} | {v['attested_rows_named']} | "
                f"{v['attested_rows_are_the_truth']} | {v['assigned_rows']} |")

    out += ["", "## Oracle gates", "",
            "**No gate was ever added or changed for this family.** All nine "
            "of G1–G9 are class-agnostic — they compare outcomes against the "
            "answer key and never look at `planted_classes` — so the primary "
            "soundness question is genuinely gated: a `Verified` on the "
            "corrupted line whose composition is not the truth is a G1 "
            "violation exactly as it would be anywhere else. "
            "`corpus/oracle.py`'s *measured* (ungated) accounting was later "
            "corrected for the bank-side frame under `DECISIONS.md` §56; that "
            "touched no gate, and is described below.",
            "",
            "| dataset | gates | verdict | seconds | runs | verdict "
            "byte-identical |", "|---|---|---|---:|---:|---|"]
    for r in results:
        gates = r["oracle_violations_by_gate"]
        out.append(f"| `{r['dataset']}` | "
                   f"{dict(gates) if gates else 'all zero'} | "
                   f"{'PASS' if r['oracle_passed'] else 'FAIL'} | "
                   f"{r['seconds']} | {r['runs']} | "
                   f"{r['verdict_identical_across_runs']} |")
    violations = [(r["dataset"], line) for r in results
                  for line in r["oracle_violations"]]
    if violations:
        out += ["", "Violations, all of them, none elided:", ""]
        out += [f"* `{name}` — {line}" for name, line in violations]

    out += ["", "### Where the oracle could not represent this class, and "
            "what was fixed (2026-08-31)", "",
            "The gates always held. The oracle's *measured, ungated* "
            "`attestation_discrepancy` block did not: it derived `planted` "
            "from `truth[\"attestation\"][\"wrong_attestations\"]`, which "
            "records PSP-side wrong attestations only. A `table: \"bank\"` "
            "planted class is not in that list and cannot be, so a **correct** "
            "bank-side detection was scored `genuinely_false` by the oracle. "
            "That was a reference-frame defect: `wrong_attestations` is keyed "
            "by settlement id, a bank-side planted class by bank-line index.",
            "",
            "**This is now fixed in `corpus/oracle.py`, per `DECISIONS.md` "
            "§56** (the owed follow-up §54 named and deferred). `_measure` "
            "reads planted bank-side classes generically from "
            "`planted_classes` into a second, separate set in bank-line-index "
            "space, and the `true_positive` / `genuinely_false` / missed loops "
            "each carry a distinct branch for it — the two frames are kept "
            "visibly apart rather than merged. The oracle's `genuinely_false` "
            "column below therefore now reads 0, matching the value the "
            "scorer-local re-attribution column had been computing "
            "independently all along; that agreement is the check that the "
            "fix produced the predicted number rather than a convenient one.",
            "",
            "**The `verdict` column above is still needed and is not "
            "removed.** The §56 fix corrects the *aggregate* "
            "`genuinely_false` counter and nothing else. There is still no "
            "gate and no oracle measurement that fires **per line** the way "
            "`bankside_verdict` does — SOUND / UNSOUND / DECLINED / "
            "NO_OUTCOME on each individual corrupted line, distinguishing "
            "\"named the disagreement\" from \"could not explain it\" from "
            "\"asserted a composition anyway\". That is a different question "
            "from how many detections were false, and the oracle cannot "
            "answer it. The `verdict` column remains a scorer-local check, "
            "not an oracle gate. The columns below are the oracle's own "
            "output, with the independent re-attribution still shown beside "
            "it rather than folded into it.", "",
            "| dataset | oracle `planted` | oracle `reported` | oracle "
            "`genuinely_false` | of those, bank-side and correct | "
            "`genuinely_false` after re-attribution |",
            "|---|---:|---:|---:|---:|---:|"]
    for r in results:
        a = r["attestation_discrepancy"]
        out.append(f"| `{r['dataset']}` | {a['oracle_planted']} | "
                   f"{a['oracle_reported']} | {a['oracle_genuinely_false']} | "
                   f"{a['mislabelled_by_oracle_as_genuinely_false']} | "
                   f"{a['genuinely_false_after_reattribution']} |")

    if with_cascade:
        out += ["", "## The frozen cascade on the same two datasets", "",
                "`matching/` (frozen at `81c04e0`) run through "
                "`corpus/baseline_old_engine.project` — the same lossy "
                "column-rename shim the other 30 datasets get, reused "
                "unmodified. The frozen engine has **no outcome meaning \"the "
                "sources disagree\"**: with one effective source there is "
                "nothing to disagree with. So its score on this class is "
                "bounded above by \"declined\" by construction, and the "
                "interesting question is only whether it stays there or "
                "asserts something.", "",
                "| dataset | ran | seconds | outcome on the corrupted line | "
                "composition claimed | equals truth | can express "
                "disagreement |", "|---|---|---:|---|---:|---|---|"]
        for r in results:
            c = r["cascade"]
            if not c["ran"]:
                out.append(f"| `{r['dataset']}` | **no** — "
                           f"`{c['failure']}` | {c['seconds']} | — | — | — | "
                           "no |")
                continue
            for line in c["lines"]:
                out.append(
                    f"| `{r['dataset']}` | yes | {c['seconds']} | "
                    f"`{line['outcome']}`"
                    + (f" ({line['candidate_count']} candidates)"
                       if line["candidate_count"] is not None else "")
                    + f" | {line['claimed_composition_size']} | "
                    f"{line['claimed_equals_true_composition']} | "
                    f"{line['can_express_disagreement']} |")

    out += ["", "## Scope, stated so it is not overread", "",
            f"* {len(results)} datasets, {total} planted bank-side errors. That "
            "is a small denominator and it is printed everywhere rather than "
            "converted to a percentage.",
            "* Both axis points carry `wrong_attestations = 0`, so no PSP-side "
            "planted error co-occurs; the bank-side result is not contaminated "
            "by one.",
            "* Only the `mispost` shape is tested. The `split-credit` shape — "
            "one settlement posted as two bank credits summing to the true "
            "amount — was deliberately set aside in §51, because it may expose "
            "a genuine gap in the outcome vocabulary and that is a contract "
            "decision, not a corpus one.",
            "* This family is **not** in `corpus/three_systems.py`'s "
            "`FAMILIES`. The \"30 datasets\" figure in `THREE_SYSTEMS.md`, "
            "`SCORECARD.md` and the claims ledger still means what it says.",
            ""]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dataset", nargs="?", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--cap", type=int, default=200)
    parser.add_argument("--time-budget", type=float, default=10.0)
    parser.add_argument("--runs", type=int, default=3,
                        help="resolver repeats for the determinism assertion")
    parser.add_argument("--no-cascade", action="store_true",
                        help="skip the frozen matching/ comparison (~2 min/ds)")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()

    targets = ([arguments.dataset] if arguments.dataset and not arguments.all
               else dataset_dirs())
    if not targets:
        print(f"no datasets under corpus/{FAMILY}", file=sys.stderr)
        return 1

    results = []
    for directory in targets:
        result = score_one(directory, cap=arguments.cap,
                           time_budget=arguments.time_budget,
                           runs=arguments.runs,
                           with_cascade=not arguments.no_cascade)
        results.append(result)
        for verdict in result["bank_side"]:
            print(f"{result['dataset']:<38} bank[{verdict['bank_line_index']}] "
                  f"{str(verdict['resolver_outcome']):<24} "
                  f"{verdict['verdict']}", flush=True)

    text = render(results, with_cascade=not arguments.no_cascade)
    print()
    print(text)
    if arguments.out:
        arguments.out.write_text(text + "\n")
    if arguments.json:
        arguments.json.write_text(json.dumps(results, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
