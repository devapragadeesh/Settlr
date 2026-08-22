"""Generate the held-out dataset.

Runs `engine/generator.py` **unmodified** at the committed held-out seed
(`holdout/SEED.txt`) over a non-overlapping period, then applies ONE additive
extension the primary set does not have: settlement reversals (`h01`).

Nothing under `engine/` is written, imported-and-patched on disk, or
regenerated. The frozen generator is imported as a library and its three
period constants are rebound **on the imported module object** for the
duration of this process. That is why `engine/generator.py` stays
byte-identical while producing a different period -- verified by
`tests/test_holdout_freeze.py`.

    python3 holdout/generate_holdout.py
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))       # generator does `from simulator import`
sys.path.insert(0, str(ROOT))

import generator as G                           # noqa: E402  the FROZEN generator
from simulator import IST                       # noqa: E402

HOLDOUT = ROOT / "holdout"
DATA = HOLDOUT / "data"
TRUTH = HOLDOUT / "ground_truth"

# --- the committed seed and period, parsed from SEED.txt rather than retyped -
# Retyping them here would let this file and the committed record drift apart,
# and the committed record is the evidence.


def _committed() -> dict:
    values: dict[str, str] = {}
    for line in (HOLDOUT / "SEED.txt").read_text().splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


_C = _committed()
SEED = int(_C["HELDOUT_SEED"])
WINDOW_START = datetime.fromisoformat(_C["HELDOUT_WINDOW_START"]).replace(tzinfo=IST)
WINDOW_END = datetime.fromisoformat(_C["HELDOUT_WINDOW_END"]).replace(
    hour=23, minute=59, tzinfo=IST)
_FIRST = datetime.fromisoformat(_C["HELDOUT_FIRST_CUTOFF"])
BATCH_DATES = [datetime(_FIRST.year, _FIRST.month, _FIRST.day, 17, 0, tzinfo=IST)
               + timedelta(weeks=i) for i in range(12)]

#: how many settlement reversals to plant. The brief says 2-3; 3 is taken so
#: that a single lucky outcome cannot pass for a pattern.
REVERSALS = 3

#: bank-side lag between the credit and the return leg. NEFT returns arrive
#: within the return window rather than instantly; two calendar days is
#: `synthesized_modelled` like the rest of this class.
RETURN_LAG_DAYS = 2


# --- the reversal extension -------------------------------------------------


def _eligible_for_reversal(truth: dict, blanked_index: int) -> list[int]:
    """Batch positions that may carry a reversal, with the exclusions stated.

    Excluded, and the direction of each bias named rather than left implicit:

      * **the last two batches** -- a reversal needs a LATER cut-off to
        re-settle into. Mechanical, no bias.
      * **the blanked-UTR bank row** -- the reversal debit references UTR-A by
        construction, so a batch whose UTR column is empty cannot express the
        mechanism at all. Mechanical, no bias.
      * **ambiguous batches (c07)** -- reversing one confounds two classes and
        makes any finding unattributable. This makes the reversal case
        CLEANER, i.e. easier: if the frozen engine still mishandles it the
        finding is stronger, and if it handles it the harder combined case
        (reversal of an ambiguous batch) remains untested. Said plainly rather
        than presented as a neutral choice.
      * **batches whose re-settlement would cross a month boundary** -- fee
        accrual is aggregated per calendar month into `gstr2b.csv`, so moving
        rows into the next month would desynchronise the tax leg and
        manufacture tax exceptions that have nothing to do with reversals.
        Keeps the reversal a single isolated variable.
    """
    batches = truth["batches"]
    ambiguous = {i for i, b in enumerate(batches) if b["ambiguous"]}
    eligible = []
    for index in range(len(batches) - 2):
        if index == blanked_index or index in ambiguous:
            continue
        this_month = G.iso_date(batches[index]["formed_at"])[:7]
        next_month = G.iso_date(batches[index + 1]["formed_at"])[:7]
        if this_month != next_month:
            continue
        eligible.append(index)
    return eligible


def plant_reversals(rows, bank, truth, blanked_index, rng, mk):
    """A batch settles, the payout fails at the bank, the rows re-settle.

    Three artefacts, which together are the bank-statement shape the primary
    set does not have:

      1. the ORIGINAL credit under UTR-A, already present and left untouched;
      2. a bank DEBIT reversing it, referencing UTR-A in its narration;
      3. a NEW credit under UTR-B whose composition DUPLICATES the original's.

    The ledger rows move from settlement A to a new settlement B, because the
    recon report is a current-state snapshot and B is the settlement that
    actually paid them. Settlement A is retained in the KEY -- marked
    `reversed_by` -- since it genuinely occurred and was genuinely reversed.

    Rejected: leaving the rows attesting UTR-A and adding B as an unattested
    credit. It makes the re-settlement invisible to any consumer of the recon
    file, which is not how a merchant would see it, and it would have made the
    engine's job easier rather than harder.
    """
    batches = truth["batches"]
    eligible = _eligible_for_reversal(truth, blanked_index)
    chosen = sorted(rng.sample(eligible, min(REVERSALS, len(eligible))))

    rows_by_sid: dict[str, list] = {}
    for row in rows:
        if row["settlement_id"]:
            rows_by_sid.setdefault(row["settlement_id"], []).append(row)

    bank_by_utr = {line["utr"]: line for line in bank if line["utr"]}
    records = []

    for index in chosen:
        original = batches[index]
        utr_a = original["utr"]
        credit_a = bank_by_utr[utr_a]
        payout = original["bank_payout"]

        # (3) the re-settlement: a NEW settlement at the next cut-off.
        formed_at = batches[index + 1]["formed_at"]
        settlement_b = mk("setl")
        utr_b = f"{formed_at}{settlement_b[-6:]}"

        moved = rows_by_sid.get(original["settlement_id"], [])
        for row in moved:
            row["settlement_id"] = settlement_b
            row["settled_at"] = formed_at
            # `settlement_utr` is null on adjustment rows even with a real sid
            # (class c12). Preserve that, or the extension would silently
            # repair a planted schema quirk.
            if row["settlement_utr"] is not None:
                row["settlement_utr"] = utr_b

        # (2) the return leg: a DEBIT, negative amount, referencing UTR-A.
        returned_on = (datetime.fromisoformat(credit_a["date"])
                       + timedelta(days=RETURN_LAG_DAYS)).date().isoformat()
        reason = rng.choice([
            "RETURN-INVALID ACCOUNT NUMBER", "RETURN-ACCOUNT CLOSED",
            "RETURN-BENEFICIARY NAME MISMATCH",
        ])
        debit_line = OrderedDict(
            utr=utr_a,
            date=returned_on,
            narration=(f"NEFT-RET-RATN0000088-{reason}-"
                       f"ACME RETAIL PRIVATE LIMITED-{utr_a}"),
            amount=G.rupees(-payout),
        )
        credit_b_line = OrderedDict(
            utr=utr_b,
            date=G.iso_date(formed_at),
            narration=(f"NEFT-CR-RATN0000088-RAZORPAY SOFTWARE PVT LTD-"
                       f"ACME RETAIL PRIVATE LIMITED-{utr_b}"),
            amount=G.rupees(payout),
        )
        bank.append(debit_line)
        bank.append(credit_b_line)

        records.append(OrderedDict(
            original_settlement_id=original["settlement_id"],
            original_utr=utr_a,
            original_credit_date=credit_a["date"],
            reversal_debit_date=returned_on,
            reversal_narration_reason=reason,
            resettlement_settlement_id=settlement_b,
            resettlement_utr=utr_b,
            resettlement_formed_at=formed_at,
            resettlement_date=G.iso_date(formed_at),
            payout_paise=payout,
            row_ids=sorted(r["entity_id"] for r in moved),
        ))

        # the key keeps BOTH: A happened and was reversed, B is where the
        # money actually landed.
        original["reversed_by"] = settlement_b
        original["reversal_debit_date"] = returned_on
        batches.append(OrderedDict(
            settlement_id=settlement_b, utr=utr_b, formed_at=formed_at,
            formed_on=G.iso_date(formed_at),
            available_live_balance=original["available_live_balance"],
            credit_ids=list(original["credit_ids"]),
            debit_ids=list(original["debit_ids"]),
            selected_payment_credit=original["selected_payment_credit"],
            credit_total=original["credit_total"],
            debit_total=original["debit_total"],
            bank_payout=payout, ambiguous=False,
            tying_decompositions=[], tying_decompositions_truncated=False,
            selection_degraded=original["selection_degraded"],
            pool_size=original["pool_size"],
            classes=sorted(set(original["classes"])
                           | {"h01_settlement_reversal_resettled"}),
            resettlement_of=original["settlement_id"],
        ))
        original["credit_ids"] = []
        original["debit_ids"] = []

    bank.sort(key=lambda line: (line["date"], line["utr"]))
    return records, chosen


#: The merchant's own ERP series (`ACM/26-27/NNNN`) and Razorpay's monthly fee
#: invoice series (`RZP/BLR/26-27/NNNN`) both restart from a FIXED base in the
#: frozen generator -- they are not seeded -- so the held-out set would reuse
#: the primary set's invoice numbers verbatim. Harmless in practice, since the
#: two datasets are never loaded together, but it contradicts the stated
#: disjointness property, and a property that holds "in practice" is the kind
#: that stops holding. Both series are offset into a disjoint block here.
#:
#: Realistic as well as disjoint: the held-out period FOLLOWS the primary
#: period in the same financial year, and a merchant's invoice series is
#: continuous, so a later block is what a later period would actually carry.
SERIES_OFFSET = 1000
SERIES = (("ACM/26-27/", 4), ("RZP/BLR/26-27/", 4))


def offset_invoice_series(paths) -> int:
    """Shift every invoice number in the held-out artefacts by SERIES_OFFSET.

    Applied by regex over the emitted files so that EVERY reference moves in
    lockstep -- `erp_orders.csv`, the Razorpay lines in `gstr2b.csv`, and the
    key's `erp_orphan_invoices`, `itc_at_risk` and `gst_rounding_residuals`.
    Renumbering one and not the others would silently break the joins the tax
    leg depends on.
    """
    import re

    moved = 0
    for path in paths:
        text = original = path.read_text()
        for prefix, width in SERIES:
            pattern = re.compile(re.escape(prefix) + r"(\d{%d})" % width)
            text = pattern.sub(
                lambda m: f"{prefix}{int(m.group(1)) + SERIES_OFFSET}", text)
        if text != original:
            path.write_text(text)
            moved += 1
    return moved


def main() -> None:
    # Rebind the period on the IMPORTED module. engine/generator.py on disk is
    # never touched; the freeze test hashes it before and after.
    G.WINDOW_START = WINDOW_START
    G.WINDOW_END = WINDOW_END
    G.BATCH_DATES = BATCH_DATES

    rows, result, labels, batch_labels, counts = G.generate(SEED, DATA, TRUTH)

    # --- the h01 extension, applied to the emitted artefacts ---------------
    truth = json.loads((TRUTH / "ground_truth.json").read_text())
    recon = json.loads((DATA / "recon_combined.json").read_text())
    with (DATA / "bank_statement.csv").open(newline="") as fh:
        bank = [OrderedDict(line) for line in csv.DictReader(fh)]

    # A separate stream from the generator's own, so that planting a
    # reversal cannot perturb any value the frozen generator produced.
    rng = random.Random(SEED + 1)
    mk = G.make_id_factory(rng)
    records, chosen = plant_reversals(
        recon["items"], bank, truth,
        truth["blanked_utr_bank_row_index"], rng, mk)

    for record in records:
        for row_id in record["row_ids"]:
            truth["settled_in"][row_id] = record["resettlement_settlement_id"]
            truth["row_classes"].setdefault(row_id, [])
            truth["row_classes"][row_id] = sorted(
                set(truth["row_classes"][row_id]) | {"h01_settlement_reversal_resettled"})
    truth["settled_in"] = OrderedDict(sorted(truth["settled_in"].items()))
    truth["row_classes"] = OrderedDict(sorted(truth["row_classes"].items()))
    truth["batches"].sort(key=lambda b: (b["formed_at"], b["settlement_id"]))
    truth["planted_reversals"] = records
    truth["reversed_batch_indexes"] = chosen
    truth["holdout"] = True
    truth["holdout_spec"] = "holdout/HOLDOUT_SPEC.md"
    truth["period"] = {"ledger_start": WINDOW_START.date().isoformat(),
                       "ledger_end": WINDOW_END.date().isoformat(),
                       "first_cutoff": BATCH_DATES[0].date().isoformat(),
                       "last_cutoff": BATCH_DATES[-1].date().isoformat()}

    recon["count"] = len(recon["items"])
    G.write_json(DATA / "recon_combined.json", recon)
    G.write_json(TRUTH / "ground_truth.json", truth)
    G.write_csv(DATA / "bank_statement.csv", bank)

    offset_invoice_series([DATA / "erp_orders.csv", DATA / "gstr2b.csv",
                           TRUTH / "ground_truth.json"])
    truth = json.loads((TRUTH / "ground_truth.json").read_text())

    G.write_hashes(DATA, TRUTH)   # after the offset, so the hashes bind the
                                  # bytes that actually ship

    write_generation_report(recon["items"], truth, bank, records, counts)

    print(f"seed={SEED} rows={len(recon['items'])} "
          f"batches={len(truth['batches'])} bank_lines={len(bank)}")
    print(f"reversals planted at batch positions {chosen}")
    for record in records:
        print(f"  {record['original_utr']} -> {record['resettlement_utr']} "
              f"({len(record['row_ids'])} rows, "
              f"{G.rupees(record['payout_paise'])})")


def write_generation_report(rows, truth, bank, records, counts) -> None:
    tiers = Counter(row["source_tier"] for row in rows)
    class_counts = Counter()
    for values in truth["row_classes"].values():
        class_counts.update(values)
    for batch in truth["batches"]:
        class_counts.update(batch["classes"])

    out = ["# holdout/GENERATION_REPORT.md",
           "",
           "Written by `holdout/generate_holdout.py` from the run that produced",
           "`holdout/data/`. Every figure is derived from the emitted artefacts.",
           "",
           f"- seed: **{truth['seed']}** (committed in `holdout/SEED.txt` "
           "**before** generation -- see `git log`)",
           f"- ledger period: **{truth['period']['ledger_start']} .. "
           f"{truth['period']['ledger_end']}** "
           "(non-overlapping with the primary set)",
           f"- cut-offs: {truth['period']['first_cutoff']} .. "
           f"{truth['period']['last_cutoff']}, 12 weekly",
           f"- generator: `engine/generator.py`, **unmodified**, driven as a library",
           "",
           "| quantity | value |", "|---|---:|",
           f"| ledger rows | {len(rows)} |",
           f"| settlement batches (incl. re-settlements) | {len(truth['batches'])} |",
           f"| bank statement lines | {len(bank)} |",
           f"| of which DEBIT (reversal) lines | {sum(1 for b in bank if b['amount'].startswith('-'))} |",
           f"| ERP orders | {sum(1 for _ in open(DATA / 'erp_orders.csv')) - 1} |",
           f"| GSTR-2B lines | {sum(1 for _ in open(DATA / 'gstr2b.csv')) - 1} |",
           f"| planted settlement reversals | {len(records)} |",
           "",
           "## Class coverage",
           "",
           "The same 15 classes as the primary set, plus `h01`, which the primary",
           "set does not contain and the engine has never encountered.",
           "",
           "| class | count |", "|---|---:|"]
    for name, count in sorted(class_counts.items()):
        out.append(f"| `{name}` | {count} |")
    absent = sorted({f"c{i:02d}" for i in range(1, 16)}
                    - {name[:3] for name in class_counts})
    out += ["", f"Classes absent: **{', '.join(absent) if absent else 'none'}**",
            "", "## Provenance -- `source_tier` distribution", "",
            "| tier | rows |", "|---|---:|"]
    for tier, count in sorted(tiers.items()):
        out.append(f"| `{tier}` | {count} |")
    out += ["",
            "`h01` rows carry the tier of their underlying ledger row. The",
            "REVERSAL MECHANISM itself is `synthesized_modelled`: Razorpay",
            "documents no reversal behaviour, and `SETTLEMENT_SPEC.md` sec 10",
            "says so. See `holdout/HOLDOUT_SPEC.md` sec 2.",
            "",
            "## The planted reversals",
            "",
            "| original UTR | credited | returned | re-settled under | rows | payout |",
            "|---|---|---|---|---:|---:|"]
    for record in records:
        out.append(
            f"| `{record['original_utr']}` | {record['original_credit_date']} | "
            f"{record['reversal_debit_date']} | `{record['resettlement_utr']}` | "
            f"{len(record['row_ids'])} | {G.rupees(record['payout_paise'])} |")
    out += ["",
            "The ground-truth key records the linkage under `planted_reversals`,",
            "with `reversed_by` on the original batch and `resettlement_of` on",
            "the new one, so the relationship is recoverable in both directions.",
            ""]
    (HOLDOUT / "GENERATION_REPORT.md").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
