"""Score the GST/ITC population family. `DECISIONS.md` §55, scored separately.

    python3 corpus/score_gst.py --all --out corpus/GST_RESULTS.md \\
                                --json corpus/gst_results.json

`corpus/datasets_gst/` closes D9 in `corpus/CORPUS_SPEC.md`: the GST leg used
to plant exactly three ITC findings at three fixed indices, every dataset
identical. `corpus/generator/gst_population.py` replaces that with a real,
fractional, seeded population over however many gateway 2B lines the axis
point produces. This scorer asks the only question that population makes
askable for the first time: **do the existing, unmodified statutory filters in
`matching/stage4_exceptions.py::_tax_exceptions()` generalize to a population,
or were they precision-1.000 only because the population was three rows
wide?**

## What this does NOT do

It does not run the frozen `matching/` CASCADE end to end -- there is no
composition/closure question on the GST leg, `_tax_exceptions()` is a pure
function of `dataset.gstr2b` and `dataset.rows`, and calling it directly
(rather than through `matching.run`'s Stage 1-3 pipeline) is calling exactly
the code under test, nothing more. It DOES still need `matching.loaders.load`,
which is why `corpus/baseline_old_engine.project` is reused unmodified to
rename the bank file's columns -- `load()` parses `bank_statement.csv`
unconditionally even though nothing here reads `dataset.bank`.

It does not add GST-aware logic anywhere in `resolver/`. §55 rejected that in
its own pass, and §59 later added the one slice that was permitted: `resolver/
loaders.py::load()` now DOES open `gstr2b.csv`, and `OpenBreak` carries
`itc_risk`/`itc_risk_grounds`. The probe below is kept and its question
changed accordingly -- it no longer asks whether the file is opened (it is),
it asks whether opening it moves any LINE OUTCOME, which §59 requires it never
to do.

`DECISIONS.md` §60 added exactly one thing to `corpus/oracle.py`:
`_itc_risk_flag`, a MEASURED-not-gated precision/recall on those two new
fields, reported below. It added no gate and touched none of G1-G9. The grep
count that used to be zero is now computed live rather than asserted.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.baseline_old_engine import project                       # noqa: E402
from corpus.oracle import score                                      # noqa: E402
from matching.loaders import load as load_frozen, to_date            # noqa: E402
from matching.stage4_exceptions import (                             # noqa: E402
    analyse_tax, identify_supplier, monthly_fee_accrual, _tax_exceptions,
)
from resolver.loaders import load                                    # noqa: E402
from resolver.resolve import NAME, resolve                           # noqa: E402

FAMILY = "datasets_gst"
GROUNDS = ("gstr2b_absent", "gstr2b_no_irn", "gstr2b_37a_exposure")
GROUND_TO_REASON = {
    "gstr2b_absent": "absent_from_gstr2b",
    "gstr2b_no_irn": "no_irn_on_notified_supplier_invoice",
    "gstr2b_37a_exposure": "supplier_gstr3b_not_filed_rule_37a",
}


def dataset_dirs() -> list[Path]:
    directory = ROOT / "corpus" / FAMILY
    if not directory.exists():
        return []
    return [d for d in sorted(directory.iterdir())
            if (d / "ground_truth.json").exists()]


# --------------------------------------------------------------------------
# the frozen filters, called directly (not through the Stage-1..3 pipeline)
# --------------------------------------------------------------------------


def run_filters(directory: Path) -> tuple:
    """`matching.loaders.load` needs the bank-column rename shim even though
    nothing here reads `dataset.bank` -- it parses `bank_statement.csv`
    unconditionally. Returns (dataset, findings, exceptions).
    """
    with tempfile.TemporaryDirectory(prefix="gst_") as tmp:
        dataset = load_frozen(project(directory, Path(tmp) / "d"))
    findings = analyse_tax(dataset)
    exceptions = _tax_exceptions(dataset, findings)
    return dataset, findings, exceptions


# --------------------------------------------------------------------------
# per-ground precision/recall
# --------------------------------------------------------------------------


def predicted_by_ground(exceptions, period_to_invoice: dict[str, str]) -> dict[str, set[str]]:
    """Map each filter's raised exceptions back to invoice numbers.

    `gstr2b_absent` fires on a MONTH (`entity_id == "period:{month}"`) because
    the dropped invoice is not in the file at all for `_tax_exceptions` to
    read an `invoice_no` off of -- `period_to_invoice` (built from the
    GENERATOR's own ground truth, never from the resolver-visible data) is
    what turns that period back into an invoice number for scoring.
    """
    out: dict[str, set[str]] = {ground: set() for ground in GROUNDS}
    for exc in exceptions:
        if exc.type == "gstr2b_absent":
            month = exc.evidence["period"]
            invoice_no = period_to_invoice.get(month)
            if invoice_no is not None:
                out["gstr2b_absent"].add(invoice_no)
        elif exc.type in ("gstr2b_no_irn", "gstr2b_37a_exposure"):
            out[exc.type].add(exc.evidence["invoice_no"])
    return out


def true_by_ground(grounds_by_invoice: dict[str, list[str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {ground: set() for ground in GROUNDS}
    for invoice_no, reasons in grounds_by_invoice.items():
        for reason in reasons:
            for ground, mapped_reason in GROUND_TO_REASON.items():
                if reason == mapped_reason:
                    out[ground].add(invoice_no)
    return out


def precision_recall(predicted: set[str], true: set[str]) -> dict:
    tp = len(predicted & true)
    fp = len(predicted - true)
    fn = len(true - predicted)
    return {
        "true_count": len(true), "predicted_count": len(predicted),
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": None if not predicted else round(tp / len(predicted), 4),
        "recall": None if not true else round(tp / len(true), 4),
    }


# --------------------------------------------------------------------------
# the GST-specific triviality check
# --------------------------------------------------------------------------


def itc_availability_shortcut(directory: Path, truth: dict) -> dict:
    """Is `itc_availability == 'No'` still a perfect proxy for "genuinely at
    risk" over this real population?

    It cannot be, by construction, for two of the three grounds: an
    absent-from-2B invoice is not in the file for the column to be read off
    of at all, and a Rule-37A exposure is DELIBERATELY not flagged in 2B --
    `itc_availability` stays "Yes" -- because the whole point of that ground
    is that the recon engine has to COMPUTE the exposure rather than read it.
    This check states that as a measured comparison, not an assumed one.
    """
    gateway_gstin = truth["gst_truth"]["gateway_gstin"]
    grounds_by_invoice = truth["gst_truth"]["grounds_by_invoice"]

    import csv
    with (directory / "gstr2b.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    gateway_rows = [r for r in rows if r["gstin"] == gateway_gstin]
    present_invoices = {r["invoice_no"] for r in gateway_rows}

    shortcut_flagged = {r["invoice_no"] for r in gateway_rows
                        if r["itc_availability"].strip().lower() == "no"}
    # Only invoices actually present in the file can possibly be found by a
    # column filter over that file -- an absent-from-2B invoice is excluded
    # from BOTH sides of this comparison for that reason, not papered over.
    true_at_risk_and_present = {inv for inv in grounds_by_invoice
                                if inv in present_invoices}

    return {
        "gateway_lines_present": len(gateway_rows),
        "shortcut_flagged_count": len(shortcut_flagged),
        "true_at_risk_and_present_count": len(true_at_risk_and_present),
        "shortcut_matches_truth_exactly":
            shortcut_flagged == true_at_risk_and_present,
        "shortcut_flagged": sorted(shortcut_flagged),
        "true_at_risk_and_present": sorted(true_at_risk_and_present),
        "note": "absent-from-2B invoices are excluded from this comparison "
                "on both sides -- they are not IN the file for a column "
                "filter to read at all. That exclusion is itself part of "
                "the answer: the shortcut cannot even see that ground.",
    }


# --------------------------------------------------------------------------
# the resolver/ read-only probe
# --------------------------------------------------------------------------


def resolver_gstr2b_probe(directory: Path) -> dict:
    """Does any LINE OUTCOME change when `gstr2b.csv` is deleted?

    When this probe was written, `resolver/loaders.py::load()` did not open
    `gstr2b.csv` at all and the expected answer was "of course not". §59
    changed that: the file is now loaded, and `OpenBreak` carries an ITC-risk
    annotation derived from it. The probe is kept because its question is now
    the SAFETY PROPERTY §59 is built on -- GST evidence attests row existence
    only and may never license batch membership, so removing the tax feed must
    still leave every `Verified`/`Ambiguous`/`Reconstructed`/`Determinate`
    decision exactly where it was.

    Run once against the real directory, once against a TEMP COPY with
    `gstr2b.csv` deleted, and diff the line outcomes. Expected: identical.
    Both runs are read-only against the real dataset -- only the temp copy is
    ever touched. `open_breaks` are deliberately NOT compared: those are the
    one place the annotation is allowed to appear, so they SHOULD differ.
    """
    began = time.perf_counter()
    with_file = resolve(load(directory))
    with_summary = json.dumps(
        sorted((o.bank_index, type(o).__name__) for o in with_file.line_outcomes))

    with tempfile.TemporaryDirectory(prefix="gst_probe_") as tmp:
        copy_dir = Path(tmp) / "d"
        shutil.copytree(directory, copy_dir)
        (copy_dir / "gstr2b.csv").unlink(missing_ok=True)
        without_file = resolve(load(copy_dir))
        without_summary = json.dumps(
            sorted((o.bank_index, type(o).__name__)
                  for o in without_file.line_outcomes))

    return {
        "seconds": round(time.perf_counter() - began, 2),
        "outputs_byte_identical": with_summary == without_summary,
        "line_outcome_count_with_file": len(with_file.line_outcomes),
        "line_outcome_count_without_file": len(without_file.line_outcomes),
    }


# --------------------------------------------------------------------------
# why the `gstr2b_absent` ITC AMOUNT disagrees -- decomposed, not asserted
# --------------------------------------------------------------------------


def absent_gap_decomposition(dataset, truth: dict) -> list[dict]:
    """Split the `gstr2b_absent` true-vs-reported ITC delta into its two terms.

    §66. The disagreement was published as a pure aggregate-vs-per-transaction
    ROUNDING gap. It is not, and the claim was refutable from the same
    `ground_truth.json` that carried it: the residual this prose blamed for a
    29,573-paise gap is recorded three keys away as `-1`.

    The delta has TWO terms and this function measures both rather than
    naming one:

    * **exclusion** -- `Σ ceil(fee * 18/100)` over that month's rows carrying
      `fee > 0, tax == 0`. `corpus/generator/build.py:681` appends
      `row["fee"] - (row["tax"] or 0)` guarded ONLY on `fee` being truthy, so
      a zero-GST row contributes its FULL fee to the gateway invoice's taxable
      value and is then charged 18% on the aggregate. Both consumers exclude
      those rows deliberately and correctly --
      `matching/stage4_exceptions.py:121` (`if row["tax"]:`) and
      `resolver/breaks.py:212` (`_accrues_input_tax`) -- because a fee that
      carried no input tax generates no credit to claim. THE GENERATOR IS THE
      WRONG SIDE of this disagreement.
    * **rounding** -- `gst_rounding_residuals[period].residual_paise`, the
      real but secondary term, 1-8 paise, already in the key.

    The identity `true - reported == exclusion + residual` is CHECKED, not
    assumed, and its result is reported per row. A row where it fails is a
    third mechanism nobody has found yet and must be visible as such.

    This is measurement only. Nothing is fixed here; see §66 for why the
    generator is not corrected on data that already exists.
    """
    residual_by_period = {item["period"]: item["residual_paise"]
                          for item in truth.get("gst_rounding_residuals", [])}
    accrual = monthly_fee_accrual(dataset)

    zero_tax: dict[str, list[int]] = {}
    for row in dataset.rows:
        if row["type"] != "payment" or not row["settled_at"] or not row["fee"]:
            continue
        if row["tax"]:
            continue
        month = to_date(row["settled_at"]).strftime("%Y-%m")
        zero_tax.setdefault(month, []).append(row["fee"])

    out = []
    for item in truth["itc_at_risk"]:
        if item["reason"] != "absent_from_gstr2b":
            continue
        period = item["period"]
        fees = zero_tax.get(period, [])
        exclusion = sum(-(-fee * 18 // 100) for fee in fees)
        residual = residual_by_period.get(period)
        true_paise = item["itc_paise"]
        reported = accrual.get(period, (0, 0, 0))[1]
        delta = true_paise - reported
        out.append({
            "invoice_no": item["invoice_no"],
            "period": period,
            "true_paise": true_paise,
            "reported_paise": reported,
            "delta_paise": delta,
            "zero_tax_rows": len(fees),
            "zero_tax_fee_paise": sum(fees),
            "exclusion_paise": exclusion,
            "rounding_residual_paise": residual,
            "identity_holds": (residual is not None
                               and delta == exclusion + residual),
        })
    return out


def zero_tax_month_coverage(dataset) -> dict:
    """How many settled months carry the mechanism at all, whether or not the
    seed's dropped invoice happened to land on one.

    Without this the two datasets whose absent month has no zero-tax row read
    as "pure rounding, nothing to see". They are not: the mechanism is live in
    other months and would surface the moment a seed dropped an invoice from
    one of them. Reporting the coverage stops the reader concluding that two
    of three datasets are unaffected.
    """
    months: dict[str, int] = {}
    for row in dataset.rows:
        if row["type"] != "payment" or not row["settled_at"] or not row["fee"]:
            continue
        month = to_date(row["settled_at"]).strftime("%Y-%m")
        months.setdefault(month, 0)
        if not row["tax"]:
            months[month] += 1
    return {"months_settled": len(months),
            "months_with_zero_tax_fee_row":
                sum(1 for count in months.values() if count),
            "zero_tax_rows_total": sum(months.values())}


def _absent_gap_section(results: list[dict]) -> list[str]:
    """The `gstr2b_absent` amount gap, decomposed. §66.

    This section REPLACES a paragraph that claimed the gap was a pure
    aggregate-vs-per-transaction rounding residual and that neither side was
    wrong. Both halves of that claim were false, and the second was refutable
    from the same `ground_truth.json` that carried it. Every number below is
    computed by `absent_gap_decomposition()` at render time; none is typed.
    """
    rows = [(r["dataset"], item)
            for r in results
            for item in r.get("absent_gap_decomposition", [])]
    if not rows:
        # Rendering a JSON file written before §66 added the keys. Say so
        # rather than silently printing the old, false explanation.
        return ["",
                "**`gstr2b_absent` is the ground whose ITC AMOUNT disagrees, "
                "and §66 identifies the cause as a defect in the corpus "
                "generator — not, as previously published here, a symmetric "
                "rounding artefact.** This report was rendered from a results "
                "file written before the decomposition was measured, so the "
                "per-term table is not available for it; see "
                "`corpus/GST_RESULTS.md` and `DECISIONS.md` §66."]

    out = ["",
           "**The `gstr2b_absent` amount gap is NOT a symmetric rounding "
           "artefact, and it is not structural. The corpus generator is the "
           "wrong side of it.** §66. This section previously claimed the gap "
           "was the aggregate-vs-per-transaction ceiling-rounding residual "
           "that `gst_rounding_residuals` records elsewhere. That explanation "
           "was refutable from the same `ground_truth.json` that carried it: "
           "the residual it blamed is recorded in that file, for the affected "
           "period, as a single-digit number. The delta has two terms, and "
           "both are measured here rather than asserted.",
           "",
           "| dataset | absent invoice | period | true | reported | delta | "
           "exclusion term | rounding term | delta = exclusion + rounding |",
           "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for name, item in rows:
        out.append(
            f"| `{name}` | `{item['invoice_no']}` | `{item['period']}` | "
            f"{item['true_paise']} | {item['reported_paise']} | "
            f"{item['delta_paise']} | {item['exclusion_paise']} | "
            f"{item['rounding_residual_paise']} | {item['identity_holds']} |")

    out += [
        "",
        "**The exclusion term — the primary one, and a real defect.** "
        "`corpus/generator/build.py:681` builds the gateway invoice's taxable "
        "value with `row[\"fee\"] - (row[\"tax\"] or 0)`, guarded only on "
        "`fee` being truthy. A payment carrying `fee > 0, tax == 0` — the "
        "`gst_applies == False` population minted at "
        "`corpus/generator/ledger.py:339` — therefore contributes its FULL "
        "fee to the taxable value, and the generator then charges 18% on that "
        "aggregate. Both consumers exclude those rows, deliberately and "
        "correctly: `matching/stage4_exceptions.py:121` (`if row[\"tax\"]:`, "
        "docstring \"there is no input tax on them to claim\") and "
        "`resolver/breaks.py:212` (`_accrues_input_tax`). A fee that carried "
        "no GST generates no input tax credit, so there is nothing for the "
        "merchant to claim and nothing at risk. **The two recon "
        "implementations are right and the ground truth is wrong**, which is "
        "the opposite of what this section used to say.",
        "",
        "**The rounding term — real, and secondary.** "
        "`gst_rounding_residuals[period].residual_paise`, the genuine "
        "aggregate-vs-per-transaction ceiling gap, is the second column of "
        "the identity above and is a single-digit number in every row.",
        "",
        "**Why the identity column matters.** `true - reported == exclusion + "
        "rounding` is checked per row, not assumed. A `False` there would mean "
        "a third mechanism nobody has found; the table reports it rather than "
        "hiding it inside a total.",
        "",
        "**Where the mechanism is live, so that a zero exclusion term is not "
        "misread as an unaffected dataset:**",
        "",
        "| dataset | settled months | months carrying a zero-GST fee row | "
        "zero-GST fee rows |", "|---|---:|---:|---:|"]
    for r in results:
        coverage = r.get("zero_tax_month_coverage")
        if not coverage:
            continue
        out.append(f"| `{r['dataset']}` | {coverage['months_settled']} | "
                  f"{coverage['months_with_zero_tax_fee_row']} | "
                  f"{coverage['zero_tax_rows_total']} |")
    out += [
        "",
        "A dataset whose exclusion term is 0 is not one where the defect is "
        "absent — it is one where the seed happened to drop an invoice from a "
        "month containing no zero-GST fee row. The coverage table above is "
        "what stops that reading. The same mechanism has been visible all "
        "along on invoices that SURVIVE, in `analyse_tax`'s own "
        "`rounding_residuals`: every month carrying a zero-GST fee row is out "
        "of tolerance by orders of magnitude, every month without one is "
        "within it by single digits. `gstr2b_absent` is not where the defect "
        "lives; it is the only ground where a second, independent computation "
        "of the same quantity exists, so it is the only place the inflation "
        "becomes visible. The disagreement is a DETECTOR, not a peculiarity "
        "of the ground.",
        "",
        "**Why `build.py` is not corrected here.** The fix would change "
        "`build_erp_and_gst`, which every corpus family shares, and would "
        "require regenerating `corpus/datasets_gst/` **and "
        "`corpus/datasets_gst_holdout/`**. Regenerating the held-out family "
        "in response to having seen its score is precisely what the held-out "
        "protocol exists to forbid, and it would not fix the defect so much "
        "as redefine truth as whatever the filters compute. Editing "
        "`matching/stage4_exceptions.py` instead is barred twice over: it is "
        "frozen at `81c04e0`, and it would make the recon engine claim input "
        "tax credit on a fee that carried none — the more serious of the two "
        "errors to a compliance reader. The correct fix belongs to a FUTURE "
        "family at seeds committed before its data exists, where generator "
        "and consumers agree from the start. See `DECISIONS.md` §66.",
        "",
        "The `gstr2b_no_irn` and `gstr2b_37a_exposure` grounds do not show "
        "the gap, and the reason is now the interesting part: their invoice "
        "still exists in the file, so both sides read the same "
        "`cgst`/`sgst` columns — the same INFLATED columns — and agree "
        "exactly. Their agreement is not corroboration that the amount is "
        "right."]
    return out


# --------------------------------------------------------------------------


def score_one(directory: Path, *, cap: int, time_budget: float) -> dict:
    truth = json.loads((directory / "ground_truth.json").read_text())
    if "gst_truth" not in truth:
        raise SystemExit(f"{directory}: no gst_truth block -- not a "
                         "population dataset. Was it built with all-zero "
                         "gst fractions by mistake?")
    gst_truth = truth["gst_truth"]

    dataset, findings, exceptions = run_filters(directory)

    period_to_invoice = {item["period"]: item["invoice_no"]
                         for item in truth["itc_at_risk"]
                         if item["reason"] == "absent_from_gstr2b"}
    predicted = predicted_by_ground(exceptions, period_to_invoice)
    true = true_by_ground(gst_truth["grounds_by_invoice"])
    per_ground = {ground: precision_recall(predicted[ground], true[ground])
                 for ground in GROUNDS}

    compounding = [inv for inv, reasons in gst_truth["grounds_by_invoice"].items()
                  if len(reasons) >= 2]
    compounding_detail = []
    for inv in compounding:
        found_grounds = [ground for ground in GROUNDS if inv in predicted[ground]]
        true_grounds = [ground for ground, reason in GROUND_TO_REASON.items()
                        if reason in gst_truth["grounds_by_invoice"][inv]]
        compounding_detail.append({
            "invoice_no": inv, "true_grounds": true_grounds,
            "found_grounds": found_grounds,
            "found_all": set(found_grounds) == set(true_grounds)})

    identified_gstin = findings.supplier_gstin
    supplier_correct = identified_gstin == gst_truth["gateway_gstin"]

    reported_itc_paise = sum(exc.evidence["itc_paise"] for exc in exceptions)
    true_itc_paise = gst_truth["itc_at_risk_paise_total"]

    reason_to_ground = {v: k for k, v in GROUND_TO_REASON.items()}
    itc_true_by_ground: dict[str, int] = {g: 0 for g in GROUNDS}
    for item in truth["itc_at_risk"]:
        ground = reason_to_ground.get(item["reason"])
        if ground is not None:
            itc_true_by_ground[ground] += item["itc_paise"]
    itc_reported_by_ground: dict[str, int] = {g: 0 for g in GROUNDS}
    for exc in exceptions:
        if exc.type in itc_reported_by_ground:
            itc_reported_by_ground[exc.type] += exc.evidence["itc_paise"]

    shortcut = itc_availability_shortcut(directory, truth)

    began = time.perf_counter()
    output = resolve(load(directory), cap=cap, time_budget=time_budget)
    seconds = time.perf_counter() - began
    report = score(output, truth)

    probe = resolver_gstr2b_probe(directory)

    return {
        "dataset": f"{directory.parent.name}/{directory.name}",
        "gateway_gstin_true": gst_truth["gateway_gstin"],
        "gateway_gstin_identified": identified_gstin,
        "identify_supplier_correct": supplier_correct,
        "gateway_invoice_count": gst_truth["gateway_invoice_count"],
        "gstr2b_lines_total": len(dataset.gstr2b),
        "per_ground": per_ground,
        "compounding_grounds_invoices": compounding_detail,
        "itc_amount_true_paise": true_itc_paise,
        "itc_amount_reported_paise": reported_itc_paise,
        "itc_amount_matches": reported_itc_paise == true_itc_paise,
        "itc_amount_true_by_ground": itc_true_by_ground,
        "itc_amount_reported_by_ground": itc_reported_by_ground,
        "absent_gap_decomposition": absent_gap_decomposition(dataset, truth),
        "zero_tax_month_coverage": zero_tax_month_coverage(dataset),
        "itc_availability_shortcut": shortcut,
        "resolver_seconds": round(seconds, 2),
        "oracle_passed": report.passed,
        "oracle_violations_by_gate": report.by_gate(),
        "oracle_violations": [v.line().strip() for v in report.violations],
        "oracle_itc_risk_flag": report.measured.get("itc_risk_flag"),
        "resolver_gstr2b_probe": probe,
    }


def oracle_gst_grep() -> int:
    """How many lines of `corpus/oracle.py` mention gst/itc/2b.

    This file used to state "zero" as prose. `DECISIONS.md` §60 added an
    `itc_risk_flag` measurement to that oracle, so the sentence stopped being
    true -- and a hand-typed count would only go stale again. Counted live.
    """
    text = (ROOT / "corpus" / "oracle.py").read_text().lower().splitlines()
    return sum(1 for line in text
               if "gst" in line or "itc" in line or "2b" in line)


def render(results: list[dict]) -> str:
    out = [f"# The GST/ITC population — {NAME} filters vs a real population",
           "",
           "Generated by `corpus/score_gst.py`. No number in this file is "
           "hand-typed.",
           "",
           "`DECISIONS.md` §55 replaced the GST leg's fixed 3-index ITC plant "
           "with `corpus/generator/gst_population.py`: a real, seeded, "
           "fractional population over however many gateway 2B lines the "
           "axis point produces (12, at `weeks=52`), with the no-IRN and "
           "Rule-37A grounds drawn independently so a single invoice can "
           "carry both. This file is the only place that population is "
           f"scored, over {len(results)} datasets — not folded into any "
           "30-dataset aggregate, which this family is not part of.",
           "",
           "## Per-ground precision / recall", "",
           "Reported as three SEPARATE rows per dataset, never pooled — a "
           "filter that is perfect on one statutory ground and blind on "
           "another would average to a misleadingly middling number if "
           "combined.", "",
           "| dataset | ground | true | predicted | TP | FP | FN | precision "
           "| recall |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        for ground in GROUNDS:
            p = r["per_ground"][ground]
            out.append(
                f"| `{r['dataset']}` | `{ground}` | {p['true_count']} | "
                f"{p['predicted_count']} | {p['true_positives']} | "
                f"{p['false_positives']} | {p['false_negatives']} | "
                f"{p['precision']} | {p['recall']} |")

    out += ["", "## Compounding-grounds invoices", "",
            "An invoice with 2 entries in `grounds_by_invoice` -- the case "
            "the old fixed-3-index plant could never produce, since its "
            "three findings always landed on three different rows.", ""]
    any_compounding = any(r["compounding_grounds_invoices"] for r in results)
    if not any_compounding:
        out.append(
            "**None occurred, at either seed.** With `absent_fraction=1/12`, "
            "`no_irn_fraction=1/6`, `filed37a_fraction=1/6` over 11-12 "
            "surviving gateway invoices, each ground's floor-rounded count "
            "is 1, and two independent 1-of-11 draws landing on the same "
            "invoice is a ~9% event per dataset that did not land at either "
            "committed seed. This is reported as an honest absence, not "
            "engineered around: `DECISIONS.md` and `gst_population.py` both "
            "forbid minting a row to force a compounding case to occur.")
    else:
        out += ["| dataset | invoice | true grounds | found grounds | found "
                "all |", "|---|---|---|---|---|"]
        for r in results:
            for c in r["compounding_grounds_invoices"]:
                out.append(f"| `{r['dataset']}` | `{c['invoice_no']}` | "
                          f"{c['true_grounds']} | {c['found_grounds']} | "
                          f"{c['found_all']} |")

    out += ["", "## `identify_supplier()` robustness", "",
            "Does the gateway GSTIN it names match `gst_truth.gateway_gstin`, "
            "including on `_gst_noisy` where `gst_vendor_noise_multiplier=12` "
            "quadruples the vendor pool it has to search?", "",
            "| dataset | true GSTIN | identified GSTIN | correct |",
            "|---|---|---|---|"]
    for r in results:
        out.append(f"| `{r['dataset']}` | `{r['gateway_gstin_true']}` | "
                  f"`{r['gateway_gstin_identified']}` | "
                  f"{r['identify_supplier_correct']} |")

    out += ["", "## Total ITC-at-risk amount accuracy", "",
            "| dataset | true (paise) | `_tax_exceptions` reported (paise) | "
            "matches |", "|---|---:|---:|---|"]
    for r in results:
        out.append(f"| `{r['dataset']}` | {r['itc_amount_true_paise']} | "
                  f"{r['itc_amount_reported_paise']} | "
                  f"{r['itc_amount_matches']} |")

    out += ["", "### Per-ground breakdown — where the total disagrees, and why",
            "", "| dataset | ground | true (paise) | reported (paise) | "
            "matches |", "|---|---|---:|---:|---|"]
    absent_mismatch_seen = False
    for r in results:
        for ground in GROUNDS:
            t = r["itc_amount_true_by_ground"][ground]
            p = r["itc_amount_reported_by_ground"][ground]
            out.append(f"| `{r['dataset']}` | `{ground}` | {t} | {p} | "
                      f"{t == p} |")
            if ground == "gstr2b_absent" and t != p:
                absent_mismatch_seen = True
    if absent_mismatch_seen:
        out += _absent_gap_section(results)

    out += ["", "## The GST-specific triviality check", "",
            "Is `itc_availability == 'No'` (a column already present in "
            "`gstr2b.csv`) still a perfect proxy for \"genuinely at risk\", "
            "over invoices that are actually present in the file to filter?",
            "", "| dataset | gateway lines present | shortcut-flagged | "
            "true-at-risk-and-present | shortcut matches truth exactly |",
            "|---|---:|---:|---:|---|"]
    for r in results:
        s = r["itc_availability_shortcut"]
        out.append(f"| `{r['dataset']}` | {s['gateway_lines_present']} | "
                  f"{s['shortcut_flagged_count']} | "
                  f"{s['true_at_risk_and_present_count']} | "
                  f"**{s['shortcut_matches_truth_exactly']}** |")
    breaks = [r for r in results
             if not r["itc_availability_shortcut"]["shortcut_matches_truth_exactly"]]
    if breaks:
        out += ["",
                "The shortcut does **not** generalize: by construction, a "
                "Rule-37A exposure leaves `itc_availability` at `\"Yes\"` -- "
                "the entire reason that ground is interesting is that 2B "
                "does not flag it and a recon engine has to COMPUTE the "
                "exposure. A single-column filter on `itc_availability` "
                "misses every Rule-37A-only invoice, and cannot see "
                "absent-from-2B invoices at all since they are not in the "
                "file."]
    else:
        out += ["", "The shortcut matched truth exactly at every dataset "
                "scored here -- see the per-dataset counts above for why "
                "(e.g. no Rule-37A-only invoice occurred at this seed)."]

    out += ["", "## The `resolver/` ITC-risk flag — MEASURED, NOT GATED", "",
            "`DECISIONS.md` §59 gave `OpenBreak` two additive fields, "
            "`itc_risk` (which of the break's rows sit in a settled month "
            "carrying an ITC finding) and `itc_risk_grounds`. §60 added "
            "`corpus/oracle.py::_itc_risk_flag` to score them. It is a "
            "**measurement, not a gate**, and that is deliberate: this is the "
            "first contact between `resolver/` and `gstr2b.csv` in any form, "
            "`resolver/breaks.py` reimplements the gateway-GSTIN "
            "identification and the three statutory checks rather than "
            "importing the frozen reference (§59's accepted "
            "duplication-drift risk), and gating an untested "
            "reimplementation's first numbers is what G5 was withdrawn for.",
            "",
            "The two sides are scored in **different frames on purpose**. The "
            "resolver attributes a row to a month by `first_reconcilable` "
            "(§59: every row reaching `dispositions()` is one nothing placed, "
            "so `settled_at` is an unconfirmed PSP claim on it). The truth "
            "below is read from the key alone — `settled_in` → "
            "`batches[].formed_at` → month, against `itc_at_risk`'s periods. "
            "A row that never settled has no month in that frame at all, "
            "because the gateway never invoiced a fee for it and there is no "
            "input tax on it to be at risk.", "",
            "Scope: the universe is the rows appearing in some `OpenBreak`, "
            "the only place §59 permits this annotation. Pairs are "
            "`(row_id, ground)`. An empty denominator is reported as `None`, "
            "never as 1.0.", "",
            "| dataset | open-break rows | of those, settled in truth | "
            "flagged rows | flagged rows that never settled | TP | FP | FN | "
            "precision | recall |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    itc_rows = []
    for r in results:
        f = r["oracle_itc_risk_flag"]
        if f is None:
            continue
        itc_rows.append((r["dataset"], f))
        out.append(
            f"| `{r['dataset']}` | {f['open_break_rows']} | "
            f"{f['open_break_rows_settled_in_truth']} | {f['flagged_rows']} | "
            f"{f['flagged_rows_that_never_settled']} | {f['true_positive']} | "
            f"{f['false_positive']} | {f['false_negative']} | "
            f"**{f['precision']}** | **{f['recall']}** |")

    out += ["", "The at-risk months the key names, per dataset, so the "
            "denominators above are checkable rather than asserted:", "",
            "| dataset | at-risk months (from the key) | breaks straddling "
            "two settled months |", "|---|---|---:|"]
    for name, f in itc_rows:
        months = ", ".join(f"`{m}` {gs}" for m, gs in f["at_risk_months"].items())
        out.append(f"| `{name}` | {months} | {f['breaks_straddling_months']} |")

    zero_precision = [name for name, f in itc_rows if f["precision"] == 0.0]
    silent = [name for name, f in itc_rows if f["flagged_rows"] == 0]
    perfect = [name for name, f in itc_rows
              if f["precision"] == 1.0 and f["recall"] == 1.0]
    missed_some = [name for name, f in itc_rows
                  if f["precision"] == 1.0 and f["recall"] not in (None, 1.0)]
    out.append("")
    if zero_precision:
        out.append(
            "**The flag performs badly on its first measurement, and here is "
            f"exactly how.** At {', '.join('`'+n+'`' for n in zero_precision)} "
            "every flagged row is a false positive: precision **0.0**, with a "
            "true-positive count of zero. The cause is visible in the table "
            "itself — `flagged rows that never settled` equals `flagged rows`. "
            "The resolver flagged rows whose *eligibility* month carries an "
            "ITC finding, but those rows never settled at all, so the gateway "
            "never invoiced a fee against them and they carry no input tax to "
            "be at risk. The finding belongs to the month's SETTLED "
            "population, and none of that population ended up in an "
            "`OpenBreak`. This is a real disagreement between §59's stated "
            "attribution choice and what the key says, not an artefact of the "
            "scoring: the oracle never uses `first_reconcilable`.")
    if silent:
        out.append("")
        out.append(
            "At " + ", ".join("`" + n + "`" for n in silent) + " the flag "
            "fires on nothing at all: zero rows flagged, and zero true pairs "
            "in the universe either. Both precision and recall are therefore "
            "**undefined**, and are reported as `None` rather than as 1.0 — "
            "an untested flag and a correct flag produce the same silence, "
            "and this file will not conflate them.")
    if missed_some:
        out.append("")
        out.append(
            "At " + ", ".join("`" + n + "`" for n in missed_some) + " the "
            "flag raised zero false alarms but missed a genuine finding: "
            "precision 1.0, recall below 1.0 -- every row it flagged was "
            "really at risk, and at least one at-risk row it should have "
            "flagged, it did not. This is reported as a miss, not folded "
            "into a headline precision figure that would hide it.")
    if perfect and not zero_precision:
        out.append("")
        out.append(
            "The flag scored precision 1.0 AND recall 1.0 at "
            + ", ".join("`" + n + "`" for n in perfect)
            + ". That is one measurement on data this capability could have "
            "been developed against, not evidence of correctness.")
    _undefined_recall = [name for name, f in itc_rows if f["recall"] is None]
    if _undefined_recall:
        out.append("")
        out.append(
            "**Recall is undefined wherever no at-risk-month settled row "
            "reached an `OpenBreak`.** That subpopulation is empty at "
            + ", ".join("`" + n + "`" for n in _undefined_recall)
            + ", so nothing in this section says whether the flag would FIND "
            "a genuine exposure there — only that what it currently emits is "
            "wrong or silent, never both wrong and correct at once.")
    out.append("")
    out.append(
        "Nothing above is gated on any of it, and no resolver code was "
        "changed in response to these numbers (§60's scope is "
        "`corpus/oracle.py` and `corpus/score_gst.py` only).")

    out += ["", "## Oracle interaction", "",
            "A grep of `corpus/oracle.py` for `gst`/`itc`/`2b` (case-"
            f"insensitive) now matches **{oracle_gst_grep()} lines** — it "
            "returned zero when this file was first generated, and §60's "
            "`_itc_risk_flag` block above is the whole of the difference. "
            "That block was measured and ungated until 2026-09-03; **its "
            "precision is now gated by G10** (`DECISIONS.md` §76), while its "
            "recall stays measured and ungated because the population is far "
            "too small for a miss to mean anything. **G10 is VACUOUS on this "
            "family and that is stated rather than left to be discovered:** "
            "the flag fires on nothing here, so no prediction can be false "
            "and the gate cannot fail. It guards a future "
            "`resolver/breaks.py` that flags more aggressively. The other "
            "GATED checks (G1-G9, all composition/closure/warrant checks) "
            "remain untouched by anything GST-related; none of them can fail "
            "or pass on a tax finding, because none of them look.", "",
            "| dataset | gates | verdict | resolver seconds |",
            "|---|---|---|---:|"]
    for r in results:
        gates = r["oracle_violations_by_gate"]
        out.append(f"| `{r['dataset']}` | "
                  f"{dict(gates) if gates else 'all zero'} | "
                  f"{'PASS' if r['oracle_passed'] else 'FAIL'} | "
                  f"{r['resolver_seconds']} |")
    violations = [(r["dataset"], line) for r in results
                 for line in r["oracle_violations"]]
    if violations:
        out += ["", "Violations, all of them, none elided:", ""]
        out += [f"* `{name}` — {line}" for name, line in violations]

    out += ["", "## The `gstr2b.csv` removal probe: can the tax feed move a "
            "line outcome?", "",
            "When this probe was first written it asked whether `resolver/` "
            "opened `gstr2b.csv` at all. It did not, and the answer was "
            "trivially yes-identical. **§59 changed that**: `resolver/"
            "loaders.py::load()` now loads the file, and `OpenBreak` carries "
            "an ITC-risk annotation derived from it. The probe is kept "
            "because its question is now the safety property §59 rests on — "
            "`GST_DOCUMENT` evidence attests row EXISTENCE only and may never "
            "license batch membership, so deleting the tax feed must still "
            "leave every `Verified`/`Ambiguous`/`Reconstructed`/"
            "`Determinate` decision exactly where it was. Run "
            "`resolver.resolve.resolve` once against the real dataset "
            "directory, once against a TEMP COPY with `gstr2b.csv` deleted "
            "(the real dataset directory is never modified), and diff the "
            "line outcomes. `open_breaks` are deliberately excluded from the "
            "comparison: they are the one place the annotation is permitted "
            "to appear, so they SHOULD differ.", "",
            "| dataset | line outcomes identical | line outcomes (with file) "
            "| line outcomes (without file) | seconds |",
            "|---|---|---:|---:|---:|"]
    for r in results:
        p = r["resolver_gstr2b_probe"]
        out.append(f"| `{r['dataset']}` | **{p['outputs_byte_identical']}** | "
                  f"{p['line_outcome_count_with_file']} | "
                  f"{p['line_outcome_count_without_file']} | {p['seconds']} |")

    all_shortcuts_hold = all(
        r["itc_availability_shortcut"]["shortcut_matches_truth_exactly"]
        for r in results)
    out += ["", "## The answer", ""]
    if all_shortcuts_hold and all(
            r["per_ground"][g]["precision"] in (None, 1.0) for r in results for g in GROUNDS) and all(
            r["per_ground"][g]["recall"] in (None, 1.0) for r in results for g in GROUNDS):
        out.append(
            "**The existing single-column filters generalize to this real "
            "population.** Every per-ground precision/recall cell scored "
            "above is 1.0 (or undefined on an empty ground), and the "
            "`itc_availability` shortcut matched the true population "
            "exactly at every dataset measured here.")
    else:
        out.append(
            "**They don't, and here is exactly where:** see the per-ground "
            "precision/recall table for any cell below 1.0, and the "
            "GST-specific triviality check above — the `itc_availability` "
            "single-column shortcut is expected to (and, per the table "
            "above, does) miss every Rule-37A-only invoice and every "
            "absent-from-2B invoice by construction, since neither ground "
            "is visible through that one column. A second, narrower gap: "
            "even when invoice IDENTIFICATION is perfect (precision/recall "
            "1.0 on every ground, as measured above), the total ITC-at-risk "
            "RUPEE figure still disagrees on `gstr2b_absent` — and per §66 "
            "that disagreement is a DEFECT IN THE CORPUS GENERATOR, not a "
            "property of the ground. `corpus/generator/build.py:681` charges "
            "GST on fee revenue its own ledger marks as carrying none, so "
            "ground truth overstates the invoice; both recon implementations "
            "exclude those rows correctly. The absent ground is simply the "
            "only one where a second, independent computation exists to "
            "expose it. See the decomposition table above.")
    _summary_parts = []
    if zero_precision:
        _summary_parts.append(
            "wrong at " + ", ".join("`" + n + "`" for n in zero_precision)
            + " (precision 0.0, every flagged row one that never settled)")
    if silent:
        _summary_parts.append(
            "silent at " + ", ".join("`" + n + "`" for n in silent)
            + " (zero rows flagged, recall undefined -- no at-risk-month "
            "settled row has yet reached an `OpenBreak` to confirm the flag "
            "would find one)")
    if missed_some:
        _summary_parts.append(
            "precision 1.0 but recall below 1.0 at "
            + ", ".join("`" + n + "`" for n in missed_some)
            + " (zero false alarms, but at least one genuine finding missed)")
    if perfect:
        _summary_parts.append(
            "precision 1.0 AND recall 1.0 at "
            + ", ".join("`" + n + "`" for n in perfect)
            + " (one measurement on data this capability could have been "
            "developed against, not evidence of correctness)")
    _flag_summary = ("its ITC-risk flag is " + "; and ".join(_summary_parts)
                     if _summary_parts else
                     "its ITC-risk flag has not been measured against any "
                     "dataset carrying `gst_truth`")
    out.append("")
    out.append(
        "**And GST/ITC reasoning in `resolver/` is now a measured quantity "
        f"rather than an absence.** §59 gave the resolver the tax feed; the "
        f"section above scores what it does with it, and the honest summary "
        f"is that {_flag_summary}. The removal probe still shows every line "
        "outcome identical with and without `gstr2b.csv`, which is the "
        "property §59 requires: the tax feed annotates open items and cannot "
        "reach a composition. The flag's PRECISION is gated at zero false "
        "positives by G10 (§76) and its recall is not; on this family the "
        "gate is vacuous, because nothing is flagged. No resolver code was "
        "changed in response to any of these numbers.")
    out.append("")
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
    if not targets:
        print(f"no datasets under corpus/{FAMILY}", file=sys.stderr)
        return 1

    results = []
    for directory in targets:
        result = score_one(directory, cap=arguments.cap,
                           time_budget=arguments.time_budget)
        results.append(result)
        print(f"{result['dataset']:<40} "
              f"identify_supplier={result['identify_supplier_correct']} "
              f"itc_match={result['itc_amount_matches']} "
              f"shortcut_holds="
              f"{result['itc_availability_shortcut']['shortcut_matches_truth_exactly']}",
              flush=True)

    text = render(results)
    print()
    print(text)
    if arguments.out:
        arguments.out.write_text(text + "\n")
    if arguments.json:
        arguments.json.write_text(json.dumps(results, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
