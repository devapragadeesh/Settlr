"""Score a resolver against the corpus. THIS side of the isolation boundary.

    python3 corpus/score_resolver.py --all

`resolver/` cannot read a `ground_truth.json` -- enforced by
`resolver/tests/test_isolation.py`, which has been watched to fail. This module
can, because scoring is what it is for. The split is the whole argument: the
thing being measured and the thing doing the measuring are different packages
with different permissions, and the permission is expressed in code rather than
in a convention.

`corpus/oracle.py` does the scoring and shares no code with the resolver.

**The resolver is frozen before this runs.** Its commit precedes this one in
`git log`. Tuning a resolver after seeing oracle output destroys the only thing
the measurement is for, so the ordering is the evidence -- the same protocol as
`holdout/SEED.txt` and `corpus/SEEDS.txt`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.oracle import (determined_instances, reconstructible_instances,  # noqa: E402
                           score)
from resolver.loaders import load                                  # noqa: E402
from resolver.resolve import NAME, resolve                         # noqa: E402

FAMILIES = ("datasets", "datasets_v2")


def dataset_dirs() -> list[Path]:
    out: list[Path] = []
    for family in FAMILIES:
        directory = ROOT / "corpus" / family
        if directory.exists():
            out += [d for d in sorted(directory.iterdir())
                    if (d / "ground_truth.json").exists()]
    return out


def score_one(directory: Path, *, cap: int, time_budget: float) -> dict:
    began = time.perf_counter()
    output = resolve(load(directory), cap=cap, time_budget=time_budget)
    seconds = time.perf_counter() - began
    truth = json.loads((directory / "ground_truth.json").read_text())
    report = score(output, truth)

    planted = truth["planted_classes"]
    false_ids = {item["settlement_id"]
                 for item in planted.get("d11_false_settlement_id", {})
                 .get("detail", [])}
    by_line = {batch["bank_line_index"]: batch for batch in truth["batches"]
               if batch.get("bank_line_index") is not None}
    caught = 0
    for outcome in output.line_outcomes:
        batch = by_line.get(outcome.bank_index)
        if batch and batch["settlement_id"] in false_ids and \
                type(outcome).__name__ == "AttestationDiscrepancy":
            caught += 1

    return {
        "dataset": f"{directory.parent.name}/{directory.name}",
        "family": directory.parent.name,
        "seconds": round(seconds, 2),
        "passed": report.passed,
        "violations_by_gate": report.by_gate(),
        "violations": [v.line().strip() for v in report.violations[:12]],
        "measured": report.measured,
        "false_settlement_id_planted": len(false_ids),
        "false_settlement_id_caught": caught,
        "bank_lines": len(truth["bank_lines"]),
        "rendered": report.render(),
    }


def render(results: list[dict]) -> str:
    out = [f"# ORACLE -- {NAME}", "",
           "Scored by `corpus/oracle.py`, which shares no code with the "
           "resolver. The resolver was committed before this ran.", "",
           "## Gates -- every one of these must be zero", "",
           f"{'dataset':<34}{'G1':>4}{'G2':>4}{'G3':>4}{'G4':>4}{'G6':>4}"
           f"{'G7':>4}{'G8':>4}{'G9':>4}   verdict"]
    out.append("-" * 78)
    totals: Counter[str] = Counter()
    for r in results:
        gates = r["violations_by_gate"]
        totals.update(gates)
        out.append(f"{r['dataset']:<34}"
                   + "".join(f"{gates.get(g, 0):>4}"
                             for g in ("G1", "G2", "G3", "G4", "G6", "G7", "G8", "G9"))
                   + f"   {'PASS' if r['passed'] else 'FAIL'}")
    out.append("-" * 78)
    out.append(f"{'TOTAL':<34}"
               + "".join(f"{totals.get(g, 0):>4}"
                         for g in ("G1", "G2", "G3", "G4", "G6", "G7", "G8", "G9")))
    out += ["", "## Measured, not gated", ""]
    out.append(f"{'dataset':<34}{'V':>4}{'nd':>4}{'AD':>4}{'R':>4}{'Amb':>5}"
               f"{'Unr':>5}{'mean k':>9}{'max k':>7}{'det':>6}{'rec':>6}")
    out.append("-" * 88)
    for r in results:
        accounting = r["measured"]["accounting"]
        determined = r["measured"]["determined"]
        out.append(
            f"{r['dataset']:<34}{accounting['verified']:>4}"
            f"{accounting['verified_non_decisive']:>4}"
            f"{accounting['attestation_discrepancy']:>4}"
            f"{accounting['reconstructed']:>4}{accounting['ambiguous']:>5}"
            f"{accounting['unresolved']:>5}"
            f"{accounting['mean_candidate_set_size']:>9.2f}"
            f"{accounting['max_candidate_set_size']:>7}"
            f"{determined['determined_resolved']:>3}/"
            f"{determined['determined_instances']:<2}"
            f"{determined['reconstructible_resolved']:>3}/"
            f"{determined['reconstructible_instances']:<2}")

    # --- row disposition: the claim and the queue, never summed together ---
    out += ["", "## Row disposition (contract 4.7)", "",
            "`ProvenUnmatched` asserts; `OpenBreak` does not. They are never "
            "added together -- a total over both is exactly the conflation the "
            "amendment undoes.", "",
            f"{'dataset':<34}{'proven':>7}{'G9':>4}{'open':>7}{'clust':>7}"
            f"{'causes':>7}{'/cause':>7}{'0-30':>6}{'31-60':>6}{'61-90':>6}"
            f"{'90+':>6}{'unexpl':>7}"]
    out.append("-" * 104)
    agg: Counter[str] = Counter()
    for r in results:
        pu = r["measured"]["proven_unmatched"]
        ob = r["measured"]["open_break"]
        age = ob["by_age"]
        agg["proven"] += pu["rows"]; agg["g9"] += pu["row_settled_after_all"]
        agg["open"] += ob["rows"]; agg["clustered"] += ob["clustered_rows"]
        agg["causes"] += ob["distinct_causes"]
        agg["unexplained"] += ob["by_reason"].get("unexplained", 0)
        for k, v in age.items():
            agg[k] += v
        out.append(
            f"{r['dataset']:<34}{pu['rows']:>7}{pu['row_settled_after_all']:>4}"
            f"{ob['rows']:>7}{ob['clustered_rows']:>7}{ob['distinct_causes']:>7}"
            f"{ob['rows_per_cause']:>7.1f}"
            + "".join(f"{age.get(k, 0):>6}" for k in ("0-30", "31-60", "61-90", "90+"))
            + f"{ob['by_reason'].get('unexplained', 0):>7}")
    out.append("-" * 104)
    out.append(f"{'TOTAL':<34}{agg['proven']:>7}{agg['g9']:>4}{agg['open']:>7}"
               f"{agg['clustered']:>7}{agg['causes']:>7}"
               f"{(agg['clustered'] / agg['causes'] if agg['causes'] else 0):>7.1f}"
               + "".join(f"{agg.get(k, 0):>6}"
                         for k in ("0-30", "31-60", "61-90", "90+"))
               + f"{agg['unexplained']:>7}")

    # --- the four-way discrepancy split ---------------------------------
    out += ["", "## `AttestationDiscrepancy` — the four-way split", "",
            "`reported − planted` is **not** a false-alarm rate. A bank debit "
            "revoking an earlier credit is a genuine cross-party "
            "contradiction; it is simply not one the corpus planted. Each is "
            "checked against a `reversal_debit` line in the answer key rather "
            "than assumed.", "",
            "| | count |", "|---|---:|"]
    ads = lambda k: sum(r["measured"]["attestation_discrepancy"].get(k, 0)
                        for r in results)
    out += [f"| reported | {ads('reported')} |",
            f"| planted and found | {ads('correctly_identified')} |",
            f"| **true finding of another kind** (reversal, corroborated) | "
            f"**{ads('true_finding_of_another_kind')}** |",
            f"| **genuinely false** | **{ads('genuinely_false')}** |",
            f"| planted but missed | "
            f"{ads('planted') - ads('correctly_identified')} |"]
    missed = [(r["dataset"], sid)
              for r in results
              for sid in r["measured"]["attestation_discrepancy"].get(
                  "planted_but_missed", [])]
    if missed:
        out += ["", "Planted discrepancies missed, by settlement id:", ""]
        out += [f"* `{sid}` in `{name}`" for name, sid in missed]
    bogus = [(r["dataset"], d)
             for r in results
             for d in r["measured"]["attestation_discrepancy"].get(
                 "genuinely_false_detail", [])]
    out += ["", ("Genuinely false findings: " + ", ".join(
        f"`{name}` {d}" for name, d in bogus)) if bogus
        else "**No genuinely false findings.** The false-alarm rate is zero."]

    out += ["", "### `OpenBreak` by reason, all datasets", ""]
    reasons: Counter[str] = Counter()
    for r in results:
        reasons.update(r["measured"]["open_break"]["by_reason"])
    out.append(f"{'reason':<24}{'rows':>8}   owner / closes when")
    from resolver_contract.types import BREAK_ROUTING, BreakReason
    for reason, n in reasons.most_common():
        owner, closes = BREAK_ROUTING[BreakReason(reason)]
        out.append(f"{reason:<24}{n:>8}   {owner} / {closes}")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dataset", nargs="?", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--cap", type=int, default=200)
    parser.add_argument("--time-budget", type=float, default=10.0)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()

    targets = ([arguments.dataset] if arguments.dataset and not arguments.all
               else dataset_dirs())
    results = []
    for directory in targets:
        result = score_one(directory, cap=arguments.cap,
                           time_budget=arguments.time_budget)
        results.append(result)
        gates = result["violations_by_gate"]
        print(f"{result['dataset']:<34} "
              f"{'PASS' if result['passed'] else 'FAIL'}  {dict(gates)}",
              flush=True)
    text = render(results)
    print()
    print(text)
    if arguments.out:
        arguments.out.write_text(text + "\n")
    if arguments.json:
        arguments.json.write_text(
            json.dumps([{k: v for k, v in r.items() if k != "rendered"}
                        for r in results], indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
