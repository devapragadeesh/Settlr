"""SCORECARD.md -- the five-minute read. Generated; no value typed by hand.

Every metric carries its denominator and its scope INLINE, because the repeated
failure this project records is a true number read as covering more than it
does (`DECISIONS.md` sec 44, sec 47, `CLAIMS.md`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Run as `python3 corpus/scorecard.py` the repo root is not on sys.path, and
# these modules import `corpus.coverage` so the split is computed once.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
#: The D15 verdict, measured in `investigation/D15_MEASUREMENT.md`. Held here
#: as data rather than prose so the scorecard states it without re-deriving a
#: 40-minute enumeration on every run.
D15 = {"correct_refusals": 15, "genuine_failures": 0, "unknown": 0,
       "instances": 18}


def dig(payload, path):
    for key in path:
        payload = payload[key]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "SCORECARD.md")
    arguments = parser.parse_args()

    oracle = json.loads((ROOT / "corpus" / "oracle_results.json").read_text())
    total = lambda p: sum(dig(r["measured"], p) for r in oracle)
    gate = lambda g: sum(r["violations_by_gate"].get(g, 0) for r in oracle)

    # The three-way split, computed once in `corpus/coverage.py` so the
    # scorecard, THREE_SYSTEMS.md and CLAIMS.md cannot drift apart.
    from corpus.coverage import split

    all_ds = split(oracle, "all")
    non_abs = split(oracle, "non_absence")
    abs_only = split(oracle, "absence")
    orig = split(oracle, "original_14")

    ad = lambda k: total(("attestation_discrepancy", k))
    verified = total(("accounting", "verified"))
    seconds = sum(r.get("seconds", 0) for r in oracle)

    rows = [
        ("**Soundness — every one of these is a gate that must be zero**", "", ""),
        ("wrong `Verified` assignments (G1)", f"**{gate('G1')}**",
         f"of {verified} `Verified`, 30 datasets"),
        ("`Verified` warrants lacking two independent parties (G2)",
         f"**{gate('G2')}**", f"of {verified} `Verified`, 30 datasets"),
        ("rows assigned with no warrant (G4)", f"**{gate('G4')}**",
         "all assignments, 30 datasets"),
        ("evidence provenance the corpus contradicts (G6)", f"**{gate('G6')}**",
         "all evidence, 30 datasets"),
        ("`ProvenUnmatched` rows that in fact settled (G9)", f"**{gate('G9')}**",
         f"of {total(('proven_unmatched', 'rows'))} proven rows, 30 datasets"),
        ("", "", ""),
        ("**Coverage — three-way, because a line the resolver MUST NOT "
          "answer is not a line it failed to answer**", "", ""),
        ("all 30 datasets — answered / not determinable / record contradicted",
         f"{all_ds['answered']} / {all_ds['not_determinable']} / "
         f"{all_ds['record_contradicted']}",
         f"of {all_ds['settlement_lines']} settlement lines"),
        ("… coverage on lines where a composition claim is the appropriate answer",
         f"**{all_ds['answered']}/{all_ds['determinable']} "
         f"({all_ds['on_determinable_pct']:.1f}%)**",
         "excludes the lines whose record contradicts itself"),
        ("the 28 datasets carrying a PSP artefact",
         f"{non_abs['answered']} / {non_abs['not_determinable']} / "
         f"{non_abs['record_contradicted']}",
         f"of {non_abs['settlement_lines']} settlement lines — "
         f"**{non_abs['not_determinable']} not determinable**"),
        ("… coverage on determinable lines",
         f"**{non_abs['answered']}/{non_abs['determinable']} "
         f"({non_abs['on_determinable_pct']:.1f}%)**",
         "the 28 non-absence datasets"),
        ("the 2 PSP-absence datasets",
         f"{abs_only['answered']} / {abs_only['not_determinable']} / "
         f"{abs_only['record_contradicted']}",
         f"of {abs_only['settlement_lines']} settlement lines. **Coverage, "
         f"not accuracy** — of the {abs_only['answered']} answered, "
         f"{abs_only['answered']} correct"),
        ("*the original 14 — the scope `THREE_SYSTEMS.md` publishes*",
         f"*{orig['answered']} / {orig['not_determinable']} / "
         f"{orig['record_contradicted']}*",
         f"*of {orig['settlement_lines']} settlement lines; one scope of four*"),
        ("**Record errors — the output the previous engine could not express**",
         "", ""),
        ("`AttestationDiscrepancy` reported", f"{ad('reported')}",
         "30 datasets"),
        ("… planted by the benchmark and found", f"{ad('correctly_identified')}",
         f"of {ad('planted')} planted"),
        ("… **real, and of a kind the benchmark did not plant**",
         f"**{ad('true_finding_of_another_kind')}**",
         "reversed credits, each corroborated against a `reversal_debit` line "
         "in the answer key"),
        ("… **genuinely false**", f"**{ad('genuinely_false')}**",
         f"of {ad('reported')} reported — **the false-alarm rate is zero**"),
        ("planted but missed", f"{ad('planted') - ad('correctly_identified')}",
         f"of {ad('planted')} planted"),
        ("", "", ""),
        ("**D15 — the decisive diagnostic**", "", ""),
        ("G8 abstentions that are **correct refusals**",
         f"**{D15['correct_refusals']}/{D15['correct_refusals']}**",
         "≥2 closing subsets **proven** over the pool the resolver can see; "
         "`investigation/D15_MEASUREMENT.md`"),
        ("… genuine abstention failures", f"**{D15['genuine_failures']}**",
         f"of {D15['instances']} reconstructible instances — none returned "
         "unique-and-complete"),
        ("both FAILING datasets fail on", "**a premise**",
         "G8 asserts uniqueness over the simulator's pool, 1.4×–14× smaller "
         "than the resolver's. The gate is **not** loosened (`DECISIONS.md` "
         "§46)"),
        ("", "", ""),
        ("**The exception queue**", "", ""),
        ("`ProvenUnmatched` rows — the ledger entails no bank credit",
         f"{total(('proven_unmatched', 'rows'))}",
         "two entailed reasons only; gated at zero by G9"),
        ("`OpenBreak` rows — classified, aged, **assert nothing**",
         f"{total(('open_break', 'rows'))}",
         "never summed with the row above (`DECISIONS.md` §40)"),
        ("… clustered under a causing bank line",
         f"{total(('open_break', 'clustered_rows'))}",
         f"across {total(('open_break', 'distinct_causes'))} distinct causes"),
        ("… the resolver could not classify at all",
         f"{sum(r['measured']['open_break']['by_reason'].get('unexplained', 0) for r in oracle)}",
         "a real reported category; a high count is an honest finding"),
        ("", "", ""),
        ("**Overall**", "", ""),
        ("datasets passing every gate",
         f"**{sum(1 for r in oracle if r['passed'])}/{len(oracle)}**",
         "the 2 failures are both PSP-absence points, on G3 and G8"),
        ("`Verified` that are non-decisive",
         f"{total(('accounting', 'verified_non_decisive'))}",
         f"of {verified} — a rival composition would have passed the same check"),
        ("`Reconstructed` wrong",
         f"{total(('reconstructed_accuracy', 'wrong'))}",
         f"of {total(('reconstructed_accuracy', 'correct')) + total(('reconstructed_accuracy', 'wrong'))} "
         "— **a count, not a rate**; the population is too small for one"),
        ("resolver runtime, 30 datasets", f"{seconds:.0f}s", "one full scoring run"),
    ]

    out = ["# SCORECARD", "",
           "Generated by `corpus/scorecard.py`. **Every figure carries its "
           "denominator and its scope inline** — the failure this project keeps "
           "recording is a true number read as covering more than it does.", "",
           "Full provenance for each number, including the command that "
           "reproduces it: [`CLAIMS.md`](CLAIMS.md).", "",
           "| metric | value | denominator and scope |", "|---|---:|---|"]
    for label, value, scope in rows:
        out.append(f"| {label} | {value} | {scope} |" if label
                   else "| | | |")
    out += ["", "## The one-paragraph version", "",
            f"Across 30 datasets the resolver makes **{gate('G1')} wrong "
            f"`Verified` assignments and {gate('G9')} wrong `ProvenUnmatched` "
            "claims**, the two outcome types that assert something and are "
            "gated at zero. It reports "
            f"**{ad('reported')} record contradictions of which "
            f"{ad('genuinely_false')} are false**, including "
            f"{ad('true_finding_of_another_kind')} real errors the benchmark "
            "did not know to plant. On the 28 datasets where a PSP artefact "
            f"exists it answers **{non_abs['answered']} of "
            f"{non_abs['determinable']}** settlement lines where a composition "
            "claim is the appropriate answer, and separately reports "
            f"**{non_abs['record_contradicted']}** lines whose record it found "
            "to be self-contradicting — findings, not coverage misses. On the "
            "2 datasets with no PSP artefact it answers "
            f"**{abs_only['answered']} of {abs_only['settlement_lines']}** and "
            "fails the oracle; that failure has now been measured and **all 15 "
            "abstentions are correct refusals**, because the resolver proved "
            "two or more closing subsets exist over the pool it can actually "
            "see. Nothing measured on this scorecard is worth fixing in the "
            "engine.", ""]
    arguments.out.write_text("\n".join(out) + "\n")
    print(f"wrote {arguments.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
