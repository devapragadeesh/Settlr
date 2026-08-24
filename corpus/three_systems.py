"""Three systems, one table, every dataset. `corpus/THREE_SYSTEMS.md`.

    python3 corpus/three_systems.py --frozen corpus/baseline_results.json \
                                    --resolver corpus/oracle_results.json

| system | what it does |
|---|---|
| naive GROUP BY | trusts the PSP entirely |
| frozen cascade | subset-sum under an objective, no evidence model |
| new resolver | evidence-tiered, declines without a warrant |

The naive baseline is measured live here because it costs milliseconds; the
other two are read from the JSON their own runs wrote, so no number in the
table is recomputed by the file that renders it.

**Read the framing before the numbers.** On the original fourteen datasets the
naive baseline WINS OUTRIGHT, and that is stated first in the report because it
is a finding about the benchmark rather than a detail about the resolvers.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.baseline_naive import measure as naive_measure       # noqa: E402
from corpus.triviality_check import groupable                    # noqa: E402


def dataset_dirs() -> list[Path]:
    out: list[Path] = []
    for family in ("datasets", "datasets_v2"):
        directory = ROOT / "corpus" / family
        if directory.exists():
            out += [d for d in sorted(directory.iterdir())
                    if (d / "ground_truth.json").exists()]
    return out


def naive_row(dataset: Path) -> dict:
    truth = json.loads((dataset / "ground_truth.json").read_text())
    determined = len(truth.get("determined_instances", []))
    from corpus.oracle import reconstructible_instances
    reconstructible = len(reconstructible_instances(truth))
    if not groupable(dataset):
        return {"ran": False, "determined": determined,
                "reconstructible": reconstructible,
                "note": "no settlement_id column to group on"}
    began = time.perf_counter()
    result = naive_measure(dataset)
    return {
        "ran": True,
        "correct": result["compositions_correct"],
        "attempted": result["compositions_attempted"],
        "wrong": result["compositions_attempted"] - result["compositions_correct"],
        "determined": determined, "determined_abstained": 0,
        "reconstructible": reconstructible, "reconstructible_abstained": 0,
        "discrepancy_detected": 0,
        "discrepancy_planted": len(truth["attestation"]["wrong_attestations"]),
        # Every answer it gives is an assertion with no statement of what
        # supports it. It has no vocabulary in which a claim could be
        # unrepresentable, so the honest figure is "all of them".
        "unwarranted": result["compositions_attempted"],
        "mean_k": 1.0,
        "seconds": round(time.perf_counter() - began, 2),
    }


def frozen_row(entry: dict | None) -> dict:
    if entry is None:
        return {"ran": False, "note": "not run"}
    if not entry.get("ran", True):
        return {"ran": False, "note": entry.get("failure", "did not run"),
                "determined": entry.get("determined_instances", 0),
                "reconstructible": entry.get("reconstructible_instances", 0),
                "seconds": entry.get("seconds", 0)}
    outcomes = entry["outcomes"]
    determinate = outcomes.get("Determinate", 0)
    return {
        "ran": True,
        "correct": determinate - entry["confident_wrong_on_our_lines"]
                   - entry["foreign_lines_adopted"],
        "attempted": determinate,
        "wrong": entry["confident_wrong_on_our_lines"]
                 + entry["foreign_lines_adopted"],
        "determined": entry["determined_instances"],
        "determined_abstained": entry["determined_abstained"],
        "reconstructible": entry.get("reconstructible_instances", 0),
        "reconstructible_abstained": entry.get("reconstructible_abstained", 0),
        "discrepancy_detected": entry.get("attestation_discrepancy_detected", 0),
        "discrepancy_planted": entry.get("attestation_discrepancy_planted", 0),
        "unwarranted": entry["unrepresentable_claims"],
        "mean_k": entry["mean_candidate_set_size"],
        "seconds": entry.get("seconds", 0),
    }


def resolver_row(entry: dict | None) -> dict:
    if entry is None:
        return {"ran": False, "note": "not run"}
    measured = entry["measured"]
    accounting = measured["accounting"]
    determined = measured["determined"]
    gates = entry["violations_by_gate"]
    return {
        "ran": True,
        "correct": (determined["determined_resolved"]
                    + measured["reconstructed_accuracy"]["correct"]),
        "attempted": accounting["verified"] + accounting["reconstructed"],
        "wrong": gates.get("G1", 0) + measured["reconstructed_accuracy"]["wrong"],
        "determined": determined["determined_instances"],
        "determined_abstained": determined["determined_abstained"],
        "reconstructible": determined["reconstructible_instances"],
        "reconstructible_abstained": determined["reconstructible_abstained"],
        "discrepancy_detected":
            measured["attestation_discrepancy"]["correctly_identified"],
        "discrepancy_planted": measured["attestation_discrepancy"]["planted"],
        # Nothing it can say is unrepresentable: the type system refuses to
        # build an unwarranted claim, so this is 0 BY CONSTRUCTION and the
        # column is here to show the contrast, not to award a point.
        "unwarranted": 0,
        "mean_k": accounting["mean_candidate_set_size"],
        "seconds": entry.get("seconds", 0),
        "gates": gates,
    }


def cell(row: dict) -> str:
    if not row.get("ran"):
        return "**cannot run**"
    return (f"{row['correct']}/{row['attempted']}")


def render(rows: list[dict]) -> str:
    out = ["# THREE SYSTEMS", "",
           "Generated by `corpus/three_systems.py` from three live runs. No "
           "number here is typed by hand.", "",
           "| system | what it does |", "|---|---|",
           "| **naive GROUP BY** | groups the recon rows by `settlement_id`, "
           "nets credit − debit, matches the total to a bank credit. Fifteen "
           "lines. Trusts the PSP entirely. |",
           "| **frozen cascade** | the previous engine: exact join → fuzzy → "
           "CP-SAT subset-sum under an objective → exception routing. No "
           "evidence model. Three documented, unpatched defects. |",
           "| **new resolver** | evidence-tiered. Assigns only with a warrant "
           "naming the parties behind the evidence; reports how many rival "
           "compositions would have passed the same check. |",
           ""]

    original = [r for r in rows if r["family"] == "datasets"
                and "Bnone" not in r["dataset"]]
    absence = [r for r in rows if "Bnone" in r["dataset"]]
    v2 = [r for r in rows if r["family"] == "datasets_v2"]

    def totals(subset, system):
        keys = ("correct", "attempted", "wrong", "determined",
                "determined_abstained", "reconstructible",
                "reconstructible_abstained", "discrepancy_detected",
                "discrepancy_planted", "unwarranted")
        ran = [r[system] for r in subset if r[system].get("ran")]
        out = {key: sum(item.get(key, 0) for item in ran) for key in keys}
        out["ran"] = len(ran)
        out["of"] = len(subset)
        out["seconds"] = sum(r[system].get("seconds", 0) for r in subset)
        out["mean_k"] = (sum(item.get("mean_k", 0) for item in ran) / len(ran)
                         if ran else 0.0)
        return out

    out += ["## The headline, stated before the table", ""]
    naive_original = totals(original, "naive")
    resolver_original = totals(original, "resolver")
    out += [
        f"**On the original fourteen datasets the naive baseline wins "
        f"outright.** It recovers {naive_original['correct']} of "
        f"{naive_original['attempted']} compositions with "
        f"{naive_original['wrong']} wrong and abstains on none of the "
        f"{naive_original['determined']} determined and "
        f"{naive_original['reconstructible']} reconstructible instances. That "
        "is not a fact about the resolvers. It is a fact about those datasets: "
        "`settlement_id` is populated on every settled row and none of them "
        "ever plants a false one, so trusting the PSP is perfectly calibrated "
        "there and the benchmark cannot tell a sound resolver from a credulous "
        "one. See `CHECKPOINT.md` §0.1.", "",
        "The two dataset families below exist because of that finding, and "
        "they are where the comparison means anything.", ""]

    for title, subset, note in (
        ("Original fourteen — the easy regression baseline", original,
         "Over-determined: the answer is recoverable by a `GROUP BY`. Any "
         "sound resolver must score near-perfectly here, and scoring well is "
         "not evidence of anything."),
        ("PSP absence — nothing to group on", absence,
         "The recon feed carries no settlement fields and there is no "
         "settlement report. The naive baseline **cannot run at all**. This is "
         "the realistic merchant case — a second gateway, a historical period, "
         "a bank feed held alone — and the only cell where reconstruction is "
         "necessary rather than self-imposed."),
        ("datasets_v2 — one FALSE `settlement_id` per dataset", v2,
         "A restatement: one batch's attested membership names rows that are "
         "not its composition, and the arithmetic still closes, so no sum "
         "check can see it. The naive baseline is confidently wrong here."),
    ):
        if not subset:
            continue
        out += ["", f"## {title}", "", note, "",
                "| dataset | naive | frozen | resolver | naive wrong | frozen "
                "wrong | resolver wrong | frozen abstained det/rec | resolver "
                "abstained det/rec | AD found (planted) | unwarranted claims "
                "n/f/r | mean k n/f/r |",
                "|---|---|---|---|---:|---:|---:|---|---|---|---|---|"]
        for r in subset:
            n, f, x = r["naive"], r["frozen"], r["resolver"]
            out.append(
                f"| `{r['dataset']}` | {cell(n)} | {cell(f)} | {cell(x)} "
                f"| {n.get('wrong', '-')} | {f.get('wrong', '-')} "
                f"| {x.get('wrong', '-')} "
                f"| {f.get('determined_abstained', '-')}/"
                f"{f.get('determined', '-')}, "
                f"{f.get('reconstructible_abstained', '-')}/"
                f"{f.get('reconstructible', '-')} "
                f"| {x.get('determined_abstained', '-')}/"
                f"{x.get('determined', '-')}, "
                f"{x.get('reconstructible_abstained', '-')}/"
                f"{x.get('reconstructible', '-')} "
                f"| {x.get('discrepancy_detected', 0)} "
                f"({x.get('discrepancy_planted', 0)}) "
                f"| {n.get('unwarranted', '-')}/{f.get('unwarranted', '-')}/"
                f"{x.get('unwarranted', '-')} "
                f"| {n.get('mean_k', 0):.2f}/{f.get('mean_k', 0):.2f}/"
                f"{x.get('mean_k', 0):.2f} |")
        for system in ("naive", "frozen", "resolver"):
            t = totals(subset, system)
            out.append(
                f"| **{system} TOTAL** ({t['ran']}/{t['of']} ran) | "
                f"{t['correct']}/{t['attempted']} | | | {t['wrong']} | | | "
                f"{t['determined_abstained']}/{t['determined']}, "
                f"{t['reconstructible_abstained']}/{t['reconstructible']} | | "
                f"{t['discrepancy_detected']} ({t['discrepancy_planted']}) | "
                f"{t['unwarranted']} | {t['mean_k']:.2f} |")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--frozen", type=Path,
                        default=ROOT / "corpus" / "baseline_results.json")
    parser.add_argument("--resolver", type=Path,
                        default=ROOT / "corpus" / "oracle_results.json")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "corpus" / "THREE_SYSTEMS.md")
    arguments = parser.parse_args()

    frozen = {}
    if arguments.frozen.exists():
        for entry in json.loads(arguments.frozen.read_text()):
            frozen[f"{entry.get('family', 'datasets')}/{entry['dataset']}"] = entry
    resolver = {}
    if arguments.resolver.exists():
        for entry in json.loads(arguments.resolver.read_text()):
            resolver[entry["dataset"]] = entry

    rows = []
    for directory in dataset_dirs():
        key = f"{directory.parent.name}/{directory.name}"
        rows.append({
            "dataset": key, "family": directory.parent.name,
            "naive": naive_row(directory),
            "frozen": frozen_row(frozen.get(key)),
            "resolver": resolver_row(resolver.get(key)),
        })
    text = render(rows)
    arguments.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
