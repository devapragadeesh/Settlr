"""Assemble a corpus dataset: files, ground truth, hashes, report.

    python3 -m corpus.generator.build --list
    python3 -m corpus.generator.build A20_B100_Cmax
    python3 -m corpus.generator.build --all

## The artefacts, and why there are four rather than three

    recon_combined.json     the PSP's ledger rows. `settlement_id` ALWAYS
                            populated -- a PSP's own recon dump does not lose
                            its settlement ids.
    settlement_report.csv   the PSP's ATTESTATION, as its own artefact.
    bank_statement.csv      the BANK's record. Independent (see bank.py).
    erp_orders.csv          the merchant's sales ledger.
    gstr2b.csv              the tax authority's inward-supply statement.
    disputes.json           issuer-originated dispute records.

Splitting the attestation out of the bank file is what makes axis B
implementable at all. Two linkages are habitually conflated:

* **row -> batch**, via `settlement_id` on the recon rows. The merchant
  ledger's own claim.
* **bank line -> batch**, via a shared reference. The CROSS-SOURCE attestation,
  and the thing `stage3_solver.run` consumes.

**Axis B varies the second only.** Blanking row-level `settlement_id` would
destroy the merchant's own ledger, change the Stage-1 exact-join rate, and move
two variables at once -- so no axis-B result would be attributable to axis B.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import random
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent.parent
for candidate in (ROOT, ROOT / "engine"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from engine.simulator import IST, compute_fee                      # noqa: E402
from corpus.generator import bank as bank_module                   # noqa: E402
from corpus.generator.bank import Payout, build_bank_statement, rupees  # noqa: E402
from corpus.generator.closure import enumerate_closing_subsets     # noqa: E402
from corpus.generator.ledger import (LedgerSpec, SOURCE_REF, build_ledger,   # noqa: E402
                                     make_id_factory)
from corpus.generator.sim import CorpusConfig, simulate            # noqa: E402

DATASETS = ROOT / "corpus" / "datasets"

#: Invoice series. NEUTRAL -- the gateway's own fee invoices use the same
#: series as every other vendor, so identifying the supplier requires
#: reconciling fee totals month by month, as SETTLEMENT_SPEC.md 10 claims.
#: The frozen set prefixes them `RZP/BLR/26-27/`, which defeats that by grep.
INVOICE_SERIES = "INV/26-27/"

VENDOR_NAMES = ["Nimbus Logistics LLP", "Vertex Supply Co",
                "Tollgate Media Pvt Ltd", "Arclight Systems",
                "Sixfold Trading", "Cloverleaf Foods Pvt Ltd",
                "Harbourline Freight", "Quillmark Stationers"]

PAN_ENTITY_CHARS = "ABCFGHLJPTKE"
UNISSUABLE_ENTITY_CHAR = "X"
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# --------------------------------------------------------------------------
# axis points
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AxisPoint:
    name: str
    pool_target: int
    attestation_coverage: Fraction
    selection_rule: str
    seed: int
    #: batch cadence in days, and arrival volume -- the two upstream knobs that
    #: control pool size. NEVER a minted row.
    cadence_days: int = 7
    payments: int = 240
    weeks: int = 12
    floor_fraction: Fraction = Fraction(9, 10)
    max_pool: int = 28
    foreign_credits: int = 4
    foreign_debits: int = 3
    reversals: int = 1
    wrong_attestations: int = 1
    #: The PSP artefact is ABSENT -- no settlement_report.csv, and the recon
    #: feed carries no settlement fields at all. Not a PSP lying: a second
    #: gateway, a historical period predating the recon feed, a bank feed held
    #: alone. See SEEDS.txt addendum 1 and CORPUS_SPEC 6.5.
    psp_attestation_absent: bool = False
    #: Batches whose `settlement_id` is written onto rows that are NOT their
    #: true composition, chosen so the arithmetic still closes. See
    #: `plant_false_composition`.
    false_compositions: int = 0
    #: Which directory family this point belongs to: `datasets` or
    #: `datasets_v2`. The original fourteen are never regenerated.
    family: str = "datasets"
    note: str = ""

    @property
    def slug(self) -> str:
        return self.name


def _point(name, pool, coverage, rule, seed, **kwargs) -> AxisPoint:
    # arrival volume is the knob for pool size: pool ~ arrivals/day * cadence
    volume = {10: 130, 20: 250, 30: 370, 40: 490, 60: 730}[pool]
    # max_pool stays at the FROZEN value of 28 for every axis point, so the
    # meet-in-the-middle boundary sits in the same place everywhere and axis A
    # crosses it rather than moving it. Above it, `max_under_cap` is solved by
    # CP-SAT -- the same rule by a tractable method, asserted equal to
    # meet-in-the-middle wherever both can run -- rather than degrading to
    # FIFO, which would move axis A and axis C together.
    return AxisPoint(name=name, pool_target=pool,
                     attestation_coverage=Fraction(coverage),
                     selection_rule=rule, seed=seed, payments=volume, **kwargs)


#: A SCREENING design, not the full 5x4x3 = 60 grid. A spine at the frozen
#: configuration, then one factor moved at a time. Untested interactions are
#: named as gaps in corpus/CORPUS_SPEC.md 8 rather than left implicit.
AXIS_POINTS: list[AxisPoint] = [
    # --- spine: the frozen configuration point, reproduced ---------------
    _point("A20_B100_Cmax", 20, 1, "max_under_cap", 20260824,
           note="spine. Closest to the frozen primary set: small pool, full "
                "attestation, the documented reading (B). Any sound resolver "
                "must score near-perfectly here."),
    # --- axis A: pool size -----------------------------------------------
    _point("A10_B100_Cmax", 10, 1, "max_under_cap", 20260825),
    _point("A30_B100_Cmax", 30, 1, "max_under_cap", 20260826,
           note="the measured regime boundary: closure uniqueness collapses "
                "above ~30."),
    _point("A40_B100_Cmax", 40, 1, "max_under_cap", 20260827),
    _point("A60_B100_Cmax", 60, 1, "max_under_cap", 20260828,
           note="above max_pool, so the simulator degrades to FIFO and says "
                "so. Closure is capped and the register says THAT too."),
    # --- axis B: attestation coverage ------------------------------------
    _point("A20_B75_Cmax", 20, "3/4", "max_under_cap", 20260829),
    _point("A20_B50_Cmax", 20, "1/2", "max_under_cap", 20260830,
           note="where axis B does its real work."),
    _point("A20_B0_Cmax", 20, 0, "max_under_cap", 20260831,
           note="Verified is provably empty here (contract 6.3). Measures "
                "abstention discipline, not resolution."),
    _point("A40_B50_Cmax", 40, "1/2", "max_under_cap", 20260901,
           note="the one A x B interaction cell: the branch that produced all "
                "50 wrong rows needs coverage < 100%, and D1 needs a big pool."),
    # --- axis C: the premise-sharing test --------------------------------
    _point("A20_B100_Cfifo", 20, 1, "fifo_under_cap", 20260902),
    _point("A20_B100_Crandom", 20, 1, "random_valid", 20260903),
    _point("A40_B100_Cfifo", 40, 1, "fifo_under_cap", 20260904),
    _point("A40_B100_Crandom", 40, 1, "random_valid", 20260905,
           note="the important cell: no objective can help, at a pool size "
                "where closure is measurably non-unique."),
    _point("A20_B100_Crandom0", 20, 1, "random_valid", 20260906,
           floor_fraction=Fraction(0), note="phi=0: uniform over ALL feasible "
                "subsets. The premise-free extreme."),
]

#: --- PSP ABSENCE. Seeds committed 2026-08-24, before this data existed. ---
#:
#: The corpus as first built is solvable by a fifteen-line GROUP BY, because
#: `settlement_id` is populated on every settled row of every dataset
#: (`corpus/baseline_naive.py`). These two points are the cell where there is
#: nothing to group by: reconstruction is genuinely necessary and
#: `Reconstructed` is the only positive outcome reachable.
ABSENCE_POINTS: list[AxisPoint] = [
    _point("A20_Bnone_Cmax", 20, 0, "max_under_cap", 20260907,
           psp_attestation_absent=True, wrong_attestations=0,
           note="the PSP artefact is ABSENT, not wrong. No settlement fields "
                "on the recon rows and no settlement report at all. The naive "
                "GROUP BY cannot run here; reconstruction is the only path."),
    _point("A40_Bnone_Cmax", 40, 0, "max_under_cap", 20260908,
           psp_attestation_absent=True, wrong_attestations=0,
           note="absence at a pool size where closure is measurably "
                "non-unique. Expect Ambiguous, and that is the honest answer."),
]

#: --- datasets_v2: one FALSE settlement_id per dataset. --------------------
#:
#: A SUPERSET GENERATION, not a correction. The original fourteen are not
#: regenerated, not corrected and remain reported; these are new files in a
#: new directory at new seeds, committed before they existed. The plant is a
#: RESTATEMENT: the PSP corrected a batch and the merchant holds a stale file,
#: so one batch's `settlement_id` names rows that are not its composition and
#: the arithmetic still closes.
V2_SEEDS = {
    "A10_B100_Cmax": 20260910, "A20_B100_Cmax": 20260911,
    "A30_B100_Cmax": 20260912, "A40_B100_Cmax": 20260913,
    "A60_B100_Cmax": 20260914, "A20_B75_Cmax": 20260915,
    "A20_B50_Cmax": 20260916, "A20_B0_Cmax": 20260917,
    "A40_B50_Cmax": 20260918, "A20_B100_Cfifo": 20260919,
    "A20_B100_Crandom": 20260920, "A40_B100_Cfifo": 20260921,
    "A40_B100_Crandom": 20260922, "A20_B100_Crandom0": 20260923,
}

V2_POINTS: list[AxisPoint] = [
    dataclasses.replace(point, seed=V2_SEEDS[point.name],
                        false_compositions=1, family="datasets_v2",
                        note=(point.note + " ").strip() + " v2: one batch's "
                             "settlement_id names rows that are not its true "
                             "composition, and the arithmetic still closes.")
    for point in AXIS_POINTS
]

ALL_POINTS = AXIS_POINTS + ABSENCE_POINTS + V2_POINTS
AXIS_BY_NAME = {point.name: point for point in AXIS_POINTS + ABSENCE_POINTS}
V2_BY_NAME = {point.name: point for point in V2_POINTS}


# --------------------------------------------------------------------------
# GSTIN
# --------------------------------------------------------------------------


def gstin_checksum(first14: str) -> str:
    charset = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total = 0
    for index, character in enumerate(first14):
        value = charset.index(character) * (2 if index % 2 else 1)
        total += value // 36 + value % 36
    return charset[(36 - total % 36) % 36]


def make_gstin(rng: random.Random, state: str = "29") -> str:
    """Checksum-valid and UNISSUABLE: `X` is not in the PAN entity-type set,
    so no generated GSTIN can collide with a real registration."""
    pan = ("".join(rng.choice(LETTERS) for _ in range(3))
           + UNISSUABLE_ENTITY_CHAR
           + rng.choice(LETTERS)
           + f"{rng.randrange(10000):04d}"
           + rng.choice(LETTERS))
    body = f"{state}{pan}1Z"
    return body + gstin_checksum(body)


# --------------------------------------------------------------------------
# recon rows -- every verified schema quirk from SETTLEMENT_SPEC.md 5
# --------------------------------------------------------------------------


#: The settlement fields. They are ONE assertion written in four columns, so
#: when the PSP artefact is absent all four are absent together. Dropping only
#: `settlement_id` would leave `settled_at` as a perfect group key -- the same
#: triviality one column over, which is exactly the error CHECKPOINT 0.1
#: records.
SETTLEMENT_FIELDS = ("settlement_id", "settled", "settled_at", "settlement_utr")


def emit_rows(ledger, result, batch_by_id, reported_reference: dict[str, str],
              *, omit_settlement_fields: bool = False):
    """Rows in Razorpay's `recon/combined` shape, quirks preserved.

    `reported_reference` maps settlement_id -> the reference the PSP REPORTS,
    which is the bank's real reference where attested and a PSP-internal one
    or blank where not. It is the PSP's claim about the bank, so it is PSP
    evidence -- never independent of the settlement id beside it.
    """
    rows: list[OrderedDict] = []
    for payment in ledger.payments:
        settlement_id = result.settled_in.get(payment.id)
        batch = batch_by_id.get(settlement_id)
        rows.append(OrderedDict(
            entity_id=payment.id, type="payment", debit=0,
            credit=payment.credit if payment.captured else 0,
            amount=payment.amount, currency="INR", fee=payment.fee,
            tax=payment.tax,
            on_hold=payment.hold_from is not None and payment.hold_until is None,
            settled=bool(settlement_id), created_at=payment.created_at,
            settled_at=batch.formed_at if batch else None,
            settlement_id=settlement_id, posted_at=None, credit_type="default",
            description=payment.description, notes=payment.notes,
            payment_id=None,                        # null ON payment rows
            settlement_utr=reported_reference.get(settlement_id) or None,
            order_id=payment.order_id, order_receipt=payment.order_receipt,
            method=payment.method, card_network=payment.card_network,
            card_issuer=payment.card_issuer, card_type=payment.card_type,
            dispute_id=payment.dispute_id, source_tier=payment.source_tier,
            source_ref=payment.source_ref))

    by_id = {p.id: p for p in ledger.payments}
    for refund in ledger.refunds:
        settlement_id = result.settled_in.get(refund.id)
        batch = batch_by_id.get(settlement_id)
        parent = by_id[refund.payment_id]
        rows.append(OrderedDict(
            entity_id=refund.id, type="refund", debit=refund.amount, credit=0,
            amount=refund.amount, currency="INR", fee=0, tax=0, on_hold=False,
            settled=bool(settlement_id), created_at=refund.created_at,
            settled_at=batch.formed_at if batch else None,
            settlement_id=settlement_id, posted_at=None, credit_type="default",
            description=refund.description, notes=refund.notes,
            payment_id=refund.payment_id,           # populated ON refund rows
            settlement_utr=reported_reference.get(settlement_id) or None,
            order_id=parent.order_id, order_receipt=parent.order_receipt,
            method=parent.method, card_network=parent.card_network,
            card_issuer=parent.card_issuer, card_type=parent.card_type,
            dispute_id=None, source_tier=refund.source_tier,
            source_ref=refund.source_ref))

    for adjustment in ledger.adjustments:
        settlement_id = result.settled_in.get(adjustment.id)
        batch = batch_by_id.get(settlement_id)
        debit = adjustment.amount if adjustment.direction == "debit" else 0
        credit = 0 if adjustment.direction == "debit" else adjustment.amount
        rows.append(OrderedDict(
            entity_id=adjustment.id, type="adjustment", debit=debit,
            credit=credit, amount=adjustment.amount, currency="INR", fee=0,
            tax=0, on_hold=False, settled=bool(settlement_id),
            created_at=adjustment.created_at,
            settled_at=batch.formed_at if batch else None,
            settlement_id=settlement_id, posted_at=None,
            # `credit_type` is ABSENT on adjustment rows -- not null
            description=adjustment.description, notes=[], payment_id=None,
            settlement_utr=None,                    # null even with a real sid
            order_id=None, order_receipt=None, method=None, card_network=None,
            card_issuer=None, card_type=None, dispute_id=adjustment.dispute_id,
            source_tier=adjustment.source_tier, source_ref=adjustment.source_ref))

    if omit_settlement_fields:
        # The keys are DELETED, not nulled -- the same precedent the frozen
        # schema sets for `credit_type` on adjustment rows. A null column says
        # "this feed has settlement data and it is empty here"; an absent
        # column says "this feed does not carry settlement data", which is the
        # artefact being modelled.
        for row in rows:
            for field_name in SETTLEMENT_FIELDS:
                row.pop(field_name, None)

    rows.sort(key=lambda row: (row["created_at"], row["entity_id"]))
    return rows


# --------------------------------------------------------------------------
# The false attestation: a RESTATEMENT
# --------------------------------------------------------------------------


def plant_false_composition(batch, rows_by_id, claimed: set[str],
                            bank_value_date: date, reported_reference: dict):
    """Write this batch's `settlement_id` onto rows that are NOT its composition.

    ## Why this class had to exist

    `corpus/baseline_naive.py` scores 168/168 on the first fourteen datasets by
    grouping on `settlement_id` and netting. It does that because
    `settlement_id` is populated on every settled row and **the corpus never
    once plants a false one** -- so a resolver that simply trusts the PSP is
    perfectly calibrated, and the benchmark cannot tell it apart from a sound
    one. The epistemic argument for checking an attestation was sound and
    completely untested. This is the class that tests it.

    ## The shape: a restatement, not a lie

    PSPs do not systematically misreport composition, and claiming they do
    would be the wrong justification. What happens is a **restatement**: the
    PSP corrects a batch and the merchant is holding the stale file. So one
    batch's attested membership is a set of rows that is not what actually
    settled.

    ## The two properties, both required

    1. **The arithmetic still closes.** A subset `S` of the true composition is
       swapped for a set `T` of unclaimed rows with an identical net, found by
       CP-SAT over exact integer paise. `Sigma credit - Sigma debit` over the
       attested rows equals the bank credit exactly, so **a sum check cannot
       see this**, and neither can the naive baseline.
    2. **It is discoverable by reconciliation, not by grepping.** Every row in
       `T` was created strictly AFTER the bank's value date for this line. A
       row that did not exist when the money left cannot have been in the
       money that left. That is a contradiction between the PSP's
       `created_at` and the BANK's `value_date` -- two parties -- so finding
       it is exactly the independent check the contract's `Verified` is
       supposed to rest on, and missing it is exactly the failure it is
       supposed to catch.

    NO ROW IS MINTED (defect D5). `S` comes from the batch, `T` from rows that
    already exist and that no batch claims. If CP-SAT finds no exact swap the
    class is recorded `planted: false` with the reason, and the dataset ships
    without it.

    Returns the ground-truth record, or `None` if no exact swap exists.
    """
    from ortools.sat.python import cp_model

    composition = sorted(batch.credit_ids + batch.debit_ids)
    if len(composition) < 2:
        return None

    def net(row_id: str) -> int:
        row = rows_by_id[row_id]
        return row["credit"] - row["debit"]

    cutoff = int(datetime.combine(bank_value_date, datetime.min.time(),
                                  tzinfo=IST).timestamp()) + 86400
    donors = sorted(
        row_id for row_id, row in rows_by_id.items()
        if row_id not in claimed and row["created_at"] >= cutoff
        and (row["credit"] - row["debit"]) != 0)
    if not donors:
        return None

    model = cp_model.CpModel()
    keep_out = [model.NewBoolVar(f"s_{r}") for r in composition]
    bring_in = [model.NewBoolVar(f"t_{r}") for r in donors]
    model.Add(sum(net(r) * v for r, v in zip(composition, keep_out))
              == sum(net(r) * v for r, v in zip(donors, bring_in)))
    model.Add(sum(keep_out) >= 1)
    model.Add(sum(keep_out) <= len(composition) - 1)
    model.Add(sum(bring_in) >= 1)
    # smallest swap that works: a restatement touches a few rows, not half the
    # batch. No objective is applied to anything a resolver will ever see --
    # this one only picks among plants at generation time.
    model.Minimize(sum(keep_out) + sum(bring_in))

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = 20.0
    if solver.Solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    removed = [r for r, v in zip(composition, keep_out) if solver.Value(v)]
    added = [r for r, v in zip(donors, bring_in) if solver.Value(v)]
    assert sum(net(r) for r in removed) == sum(net(r) for r in added)

    for row_id in removed:
        row = rows_by_id[row_id]
        row["settlement_id"] = None
        row["settled"] = False
        row["settled_at"] = None
        row["settlement_utr"] = None
    for row_id in added:
        row = rows_by_id[row_id]
        row["settlement_id"] = batch.settlement_id
        row["settled"] = True
        row["settled_at"] = batch.formed_at
        # adjustment rows carry a null UTR even with a real settlement id --
        # a frozen-schema quirk, preserved here so the corrupted rows do not
        # become identifiable by having one.
        if row["type"] != "adjustment":
            row["settlement_utr"] = reported_reference.get(
                batch.settlement_id) or None

    attested = sorted(set(composition) - set(removed) | set(added))
    return {
        "settlement_id": batch.settlement_id,
        "kind": "attested_composition_names_wrong_rows",
        "true_composition": composition,
        "attested_composition": attested,
        "rows_removed": removed,
        "rows_added": added,
        "swapped_net_paise": sum(net(r) for r in removed),
        "true_payout_paise": batch.payout,
        "reported_payout_paise": batch.payout,
        "arithmetic_still_closes": True,
        "bank_value_date": bank_value_date.isoformat(),
        "detectable_by": "temporal contradiction between the PSP's created_at "
                         "and the BANK's value_date: every added row was "
                         "created after the money left. Invisible to any sum "
                         "check, including the naive baseline's.",
    }


# --------------------------------------------------------------------------
# ERP and GST -- D6's fix
# --------------------------------------------------------------------------


def _offline_reference(rng: random.Random) -> str:
    """An order id in the merchant's own format, matching no gateway payment.

    Drawn from the SAME alphabet and length as a gateway order id, so an
    orphan is distinguishable only by the absence of a payment that references
    it -- which is the reconciliation work, not a shortcut to the label.
    """
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(rng.choice(alphabet) for _ in range(14))


def build_erp_and_gst(rng: random.Random, ledger, result, rows, spec_window,
                      settled_at_of: dict[str, int] | None = None):
    """The merchant's sales ledger and the tax authority's 2B.

    D6: the invoice sequence is allocated for EVERY line up front and the
    orphan slots are sampled uniformly across it, so an orphan holds an
    ordinary number in an ordinary place. In the frozen set the six orphans
    hold the six highest numbers in a file otherwise monotone in date order --
    a rank check finds them at precision 1.000 even though a file-position
    check passes, which is why the audit tests ordinals and not just position.
    """
    merchant_gstin = make_gstin(rng, "29")
    gateway_gstin = make_gstin(rng, "29")

    settled_payments = [p for p in ledger.payments
                        if p.captured and result.settled_in.get(p.id)]
    # ERP gaps in BOTH directions. The missing-in-ERP sample is drawn from
    # SETTLED payments specifically: an unsettled payment reasonably has no
    # invoice yet, so sampling those would not test the invariant that matters
    # -- money received, nothing in the books.
    missing = set(rng.sample([p.id for p in settled_payments],
                             min(len(settled_payments) // 14 + 1,
                                 len(settled_payments))))
    invoiced = [p for p in ledger.payments
                if p.captured and p.id not in missing]
    orphan_count = max(3, len(invoiced) // 30)

    lines: list[tuple[date, str, int, bool]] = [
        (datetime.fromtimestamp(p.created_at, IST).date(), p.order_id,
         p.amount, False)
        for p in invoiced]
    for index in range(orphan_count):
        # An orphan is a real invoice for a sale that never got paid through
        # the gateway -- a counter sale, a bank transfer, a cash order. It has
        # an order reference in the MERCHANT's system; what it lacks is a
        # matching payment.
        #
        # The first draft left `order_id` blank on orphans, and the leak audit
        # found it immediately: `order_id IS NULL/blank` isolated the class at
        # precision 1.000, recall 1.000. That is the audit doing its job on
        # this corpus rather than on the frozen one, and it is why a dataset
        # that fails its own audit does not ship.
        when = spec_window[0] + timedelta(
            days=rng.randrange((spec_window[1] - spec_window[0]).days + 1))
        lines.append((when, f"order_{_offline_reference(rng)}",
                      rng.choice([p.amount for p in invoiced]), True))
    lines.sort(key=lambda item: (item[0], item[1]))

    erp: list[OrderedDict] = []
    orphans: list[str] = []
    number = 1001
    for when, order_id, amount, is_orphan in lines:
        invoice_no = f"{INVOICE_SERIES}{number}"
        number += 1
        erp.append(OrderedDict(
            order_id=order_id, invoice_no=invoice_no,
            # most orders are B2C retail: no registration, bill of supply
            gstin=make_gstin(rng, rng.choice(["29", "27", "07", "33"]))
                  if rng.random() < 0.18 else "",
            amount=rupees(amount), invoice_date=when.isoformat()))
        if is_orphan:
            orphans.append(invoice_no)

    # --- GSTR-2B: the PURCHASE side --------------------------------------
    # Razorpay invoices MONTHLY, not per settlement, so one 2B line ties back
    # to N settlements' fee columns.
    per_month: dict[str, list[int]] = {}
    # Taken from the TRUE settlement mapping rather than from the emitted
    # column, because the column is absent at the PSP-absence axis points and
    # is deliberately corrupted at one batch in `datasets_v2`. The tax
    # authority's file is a different party's and it is correct.
    settled_at_of = settled_at_of or {}
    for row in rows:
        settled_at = settled_at_of.get(row["entity_id"])
        if row["type"] == "payment" and row["fee"] and settled_at is not None:
            month = datetime.fromtimestamp(settled_at, IST).strftime("%Y-%m")
            per_month.setdefault(month, []).append(row["fee"] - (row["tax"] or 0))

    gst_rows: list[OrderedDict] = []
    itc_at_risk: list[dict] = []
    residuals: list[dict] = []
    gateway_invoices: list[str] = []
    gst_number = 7000

    for month in sorted(per_month):
        taxable = sum(per_month[month])
        # GST computed ONCE on the aggregate; the ledger accrued it
        # ceiling-rounded per transaction. The gap is a genuine residual.
        cgst = -(-taxable * 9 // 100)
        accrued = sum(-(-value * 18 // 100) for value in per_month[month])
        residuals.append({"period": month,
                          "aggregate_tax_paise": cgst * 2,
                          "accrued_tax_paise": accrued,
                          "residual_paise": cgst * 2 - accrued})
        invoice_no = f"{INVOICE_SERIES}{gst_number}"
        gst_number += 1
        gateway_invoices.append(invoice_no)
        gst_rows.append(OrderedDict(
            gstin=gateway_gstin, invoice_no=invoice_no,
            invoice_date=f"{month}-01", taxable_value=rupees(taxable),
            igst=rupees(0), cgst=rupees(cgst), sgst=rupees(cgst),
            irn="".join(rng.choice("0123456789abcdef") for _ in range(64)),
            irn_generated_at=f"{month}-01T09:15:00",
            gstr1_filing_period=month, supplier_gstr3b_filed="Y",
            itc_availability="Yes"))

    # third-party vendor lines: the IGST path, and a population for the
    # gateway's own lines to hide in
    for index in range(len(gst_rows) * 3 + 12):
        state = rng.choice(["27", "07", "33", "29", "24", "06"])
        taxable = rng.randrange(50_000, 3_000_000)
        interstate = state != "29"
        filed = "Y" if rng.random() > 0.12 else "N"
        has_irn = rng.random() > 0.10
        gst_rows.append(OrderedDict(
            gstin=make_gstin(rng, state),
            invoice_no=f"{INVOICE_SERIES}{gst_number}", invoice_date="",
            taxable_value=rupees(taxable),
            igst=rupees(-(-taxable * 18 // 100) if interstate else 0),
            cgst=rupees(0 if interstate else -(-taxable * 9 // 100)),
            sgst=rupees(0 if interstate else -(-taxable * 9 // 100)),
            irn="".join(rng.choice("0123456789abcdef") for _ in range(64))
                if has_irn else "",
            irn_generated_at="", gstr1_filing_period="",
            supplier_gstr3b_filed=filed,
            itc_availability="Yes" if has_irn else "No"))
        gst_number += 1

    # --- the three statutory grounds, applied to GATEWAY lines -----------
    if len(gateway_invoices) >= 3:
        # Rule 37A: supplier has not filed GSTR-3B. 2B does NOT flag this --
        # itc_availability still reads Yes -- which is why it is the
        # interesting exposure: the recon engine has to COMPUTE it.
        target = gst_rows[0]
        target["supplier_gstr3b_filed"] = "N"
        itc_at_risk.append({"invoice_no": target["invoice_no"],
                            "period": target["gstr1_filing_period"],
                            "reason": "supplier_gstr3b_not_filed_rule_37a",
                            "statute": "Rule 37A CGST"})
        # Sec 16(2)(aa): the invoice never reached 2B at all
        dropped = gst_rows[1]
        gst_rows.remove(dropped)
        itc_at_risk.append({"invoice_no": dropped["invoice_no"],
                            "period": dropped["gstr1_filing_period"],
                            "reason": "absent_from_gstr2b",
                            "statute": "Sec 16(2)(aa) CGST"})
        # Rule 48(5): no valid IRN, so it is not a tax invoice
        no_irn = gst_rows[1]
        no_irn["irn"] = ""
        no_irn["itc_availability"] = "No"
        itc_at_risk.append({"invoice_no": no_irn["invoice_no"],
                            "period": no_irn["gstr1_filing_period"],
                            "reason": "no_irn_on_notified_supplier_invoice",
                            "statute": "Rule 48(5) CGST"})

    rng.shuffle(gst_rows)
    for index, row in enumerate(gst_rows):
        if not row["invoice_date"]:
            row["invoice_date"] = (spec_window[0] + timedelta(
                days=rng.randrange((spec_window[1] - spec_window[0]).days + 1))
            ).isoformat()

    return (erp, gst_rows, merchant_gstin, gateway_gstin, sorted(missing),
            orphans, itc_at_risk, residuals, gateway_invoices)


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[OrderedDict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


FROZEN_FILES = ["recon_combined.json", "disputes.json", "bank_statement.csv",
                "settlement_report.csv", "erp_orders.csv", "gstr2b.csv",
                "ground_truth.json"]


def build(point: AxisPoint, out_dir: Path | None = None) -> dict:
    out = out_dir or (ROOT / "corpus" / point.family / point.slug)
    rng = random.Random(point.seed)
    mk = make_id_factory(rng)

    start = datetime(2027, 1, 4, 0, 0, tzinfo=IST)
    window = (start, start + timedelta(weeks=point.weeks, days=3))
    batch_times = [int((start + timedelta(days=2, weeks=index)
                        ).replace(hour=17).timestamp())
                   for index in range(point.weeks)]

    spec = LedgerSpec(window_start=window[0], window_end=window[1],
                      payments=point.payments)
    ledger = build_ledger(rng, mk, spec)

    config = CorpusConfig(batch_times=batch_times, max_pool=point.max_pool,
                          selection_rule=point.selection_rule,
                          floor_fraction=point.floor_fraction,
                          rng_seed=point.seed)
    result = simulate(ledger.payments, ledger.refunds, ledger.adjustments,
                      config, id_maker=mk)
    batches = sorted(result.batches, key=lambda b: b.formed_at)
    batch_by_id = {b.settlement_id: b for b in batches}

    # ---- the bank. It is handed amounts and timestamps. Nothing else. ----
    payouts = [Payout(amount_paise=b.payout, initiated_at=b.formed_at)
               for b in batches]
    reversal_positions = sorted(rng.sample(range(len(payouts)),
                                           min(point.reversals, len(payouts))))
    bank_file = build_bank_statement(
        payouts, rng, foreign_credits=point.foreign_credits,
        foreign_debits=point.foreign_debits, reversals=reversal_positions,
        corrupt_narrations=max(2, len(payouts) // 4),
        blank_references=max(1, len(payouts) // 8))

    # ---- axis B: attestation coverage, applied to the PSP's REPORT -------
    settlement_reference: dict[str, str] = {}
    for line in bank_file.truth:
        if line.kind == "settlement" and line.payout_index is not None:
            settlement_reference[batches[line.payout_index].settlement_id] = \
                bank_file.rows[line.line_index]["bank_reference"]

    attested_count = (0 if point.psp_attestation_absent
                      else int(len(batches) * point.attestation_coverage))
    # which settlements keep attestation is a SEEDED UNIFORM SAMPLE -- not the
    # largest, not the ambiguous ones. Coverage correlated with difficulty
    # would confound the axis with the thing it is measuring.
    attested = set(rng.sample([b.settlement_id for b in batches], attested_count))
    reported: dict[str, str] = {}
    for batch in batches:
        real = settlement_reference.get(batch.settlement_id, "")
        if batch.settlement_id in attested and real:
            reported[batch.settlement_id] = real
        elif batch.settlement_id in attested:
            reported[batch.settlement_id] = ""     # bank blanked its own ref
        else:
            # The PSP reports a reference the bank never issued.
            #
            # Two earlier drafts leaked here, and the second is the instructive
            # one. Draft 1 used a distinctive `RZPX...` prefix -- an obvious
            # stage direction. Draft 2 used the right SHAPE but the wrong
            # DISTRIBUTION: a uniform 0..999999 sequence against the bank's
            # narrow running counter, and the settlement date against the
            # bank's posting date. Sorting `reported_reference` still separated
            # attested from unattested at precision 1.000, because the values
            # sorted into two bands.
            #
            # Matching the format is not enough. The value has to be drawn from
            # the same distribution the real references came from, or the
            # distribution IS the marker. So the date is a posting-like date
            # (settlement + a lag from the same range) and the sequence is
            # drawn from the observed range of this file's real bank
            # references. What is left is the only honest signal: no bank line
            # carries this reference, discoverable by looking.
            stale = (datetime.fromtimestamp(batch.formed_at, IST).date()
                     + timedelta(days=rng.choice([0, 1, 1, 2, 3])))
            low, high = _reference_range(bank_file.rows)
            reported[batch.settlement_id] = (
                f"{bank_module.BANK_PREFIX}{stale.strftime('%y')}"
                f"{stale.timetuple().tm_yday:03d}"
                f"{rng.randint(low, high):06d}")

    # ---- adversarial class: attestation that is WRONG --------------------
    wrong_attestation: list[dict] = []
    candidates = [b for b in batches
                  if b.settlement_id in attested and len(b.credit_ids) >= 3]
    for batch in rng.sample(candidates, min(point.wrong_attestations,
                                            len(candidates))):
        # the report claims an amount the batch did not pay out. A real PSP
        # report defect, and the ONLY thing that can produce
        # AttestationDiscrepancy -- an outcome the old engine could not express.
        wrong_attestation.append({
            "settlement_id": batch.settlement_id,
            "true_payout_paise": batch.payout,
            "reported_payout_paise": batch.payout + rng.choice([-1, 1])
                                     * rng.randrange(5_000, 90_000),
            "kind": "reported_amount_disagrees_with_bank"})
    wrong_by_id = {item["settlement_id"]: item for item in wrong_attestation}

    settlement_report = [
        OrderedDict(
            settlement_id=batch.settlement_id,
            reported_reference=reported[batch.settlement_id],
            reported_amount=rupees(
                wrong_by_id[batch.settlement_id]["reported_payout_paise"]
                if batch.settlement_id in wrong_by_id else batch.payout),
            initiated_at=datetime.fromtimestamp(batch.formed_at, IST)
                                 .date().isoformat(),
            status="processed")
        for batch in batches]

    rows = emit_rows(ledger, result, batch_by_id, reported,
                     omit_settlement_fields=point.psp_attestation_absent)
    (erp, gst_rows, merchant_gstin, gateway_gstin, missing_erp, orphans,
     itc_at_risk, residuals, gateway_invoices) = build_erp_and_gst(
        rng, ledger, result, rows, (window[0].date(), window[1].date()),
        settled_at_of={row_id: batch_by_id[settlement].formed_at
                       for row_id, settlement in result.settled_in.items()
                       if settlement in batch_by_id})

    # ---- the FALSE attestation, planted after ERP/GST ---------------------
    #
    # Ordering matters. `build_erp_and_gst` aggregates the fee column by
    # settlement month, and the tax authority is an independent party whose
    # file is CORRECT. Corrupting the PSP's settlement column afterwards leaves
    # GSTR-2B reflecting what really happened, which is the point of it being
    # a different party's artefact.
    rows_by_id = {row["entity_id"]: row for row in rows}
    false_compositions: list[dict] = []
    false_reason = ""
    if point.false_compositions:
        claimed = {row_id for b in batches
                   for row_id in (b.credit_ids + b.debit_ids)}
        value_date = {}
        for line in bank_file.truth:
            if line.kind == "settlement" and line.payout_index is not None:
                value_date[batches[line.payout_index].settlement_id] = date.fromisoformat(
                    bank_file.rows[line.line_index]["value_date"])
        eligible = [b for b in batches
                    if b.settlement_id in attested
                    and b.settlement_id not in wrong_by_id
                    and b.settlement_id in value_date]
        for batch in rng.sample(eligible, min(point.false_compositions,
                                              len(eligible))):
            record = plant_false_composition(
                batch, rows_by_id, claimed,
                value_date[batch.settlement_id], reported)
            if record is not None:
                false_compositions.append(record)
        if not eligible:
            false_reason = (
                "no batch is both attested and uncorrupted at this axis point, "
                "so there is no correct attestation to restate")
        elif not false_compositions:
            false_reason = (
                "no exact-net swap exists at this seed: CP-SAT found no subset "
                "of rows created after the bank's value date whose net equals "
                "the net of any subset of the sampled batch. NO ROW IS MINTED "
                "to force one (defect D5)")
    wrong_attestation += false_compositions
    wrong_by_id = {item["settlement_id"]: item for item in wrong_attestation}

    # ---- the closure register: no objective, cap far above any solver ----
    batch_truth: list[dict] = []
    determined: list[int] = []
    line_of_batch = {line.payout_index: line.line_index
                     for line in bank_file.truth if line.kind == "settlement"}
    for index, batch in enumerate(batches):
        # the EXACT pool the rule was applied to, recorded by the simulator,
        # plus the debits that were pending. A register built over a
        # RECONSTRUCTED pool measures the reconstruction, not the truth.
        pool = [(row_id, rows_by_id[row_id]["credit"] - rows_by_id[row_id]["debit"])
                for row_id in batch.pool_ids if row_id in rows_by_id]
        pool += [(row_id, rows_by_id[row_id]["credit"] - rows_by_id[row_id]["debit"])
                 for row_id in _pending_debits(rows, batch, batches, index)]
        register = enumerate_closing_subsets(pool, batch.payout,
                                             seed=point.seed)
        composition = tuple(sorted(batch.credit_ids + batch.debit_ids))
        # O(1) and ALWAYS checkable, unlike membership of a capped register:
        # does the true composition actually close? If this is ever False the
        # generator is broken, and it is asserted rather than reported.
        closes = sum(rows_by_id[r]["credit"] - rows_by_id[r]["debit"]
                     for r in composition) == batch.payout
        if not closes:
            raise AssertionError(
                f"{batch.settlement_id}: true composition does not close to "
                f"the payout -- the generator is wrong, not the data")
        entry = {
            "settlement_id": batch.settlement_id,
            "bank_line_index": line_of_batch.get(index),
            "formed_at": batch.formed_at,
            "payout_paise": batch.payout,
            "pool_size": batch.pool_size,
            "selection_degraded": batch.selection_degraded,
            "selection_fallback": getattr(batch, "selection_fallback", None),
            "sampler": getattr(batch, "sampler", "exact"),
            # FACT ABOUT THE GENERATIVE PROCESS -- always exact
            "composition": list(composition),
            # FACT ABOUT THE RECONSTRUCTION PROBLEM -- may be capped, says so
            "closure": register.to_json(),
            # THREE-VALUED. "the truth is not in the register" and "the
            # register stopped before it could look" are different statements,
            # and only the first would be a defect.
            "truth_in_closure": (register.contains(composition)
                                 if register.complete
                                 else ("yes" if register.contains(composition)
                                       else "unknown_enumeration_capped")),
            "composition_closes": closes,
        }
        batch_truth.append(entry)
        if (register.is_determined and batch.settlement_id in attested
                and batch.settlement_id not in wrong_by_id
                and entry["bank_line_index"] is not None):
            determined.append(entry["bank_line_index"])

    planted = dict(ledger.classes)
    planted.update({
        "d01_settlement_reversal": {
            "planted": bool(reversal_positions), "table": "bank",
            "members": [line.line_index for line in bank_file.truth
                        if line.kind == "reversal_debit"]},
        "d02_foreign_bank_lines": {
            "planted": point.foreign_credits + point.foreign_debits > 0,
            "table": "bank",
            "members": [line.line_index for line in bank_file.truth
                        if line.kind.startswith("foreign")]},
        # Expressed at the SETTLEMENT level, not as the rows of the batch.
        # Every batch is trivially identified by `settled_at`, so a row-level
        # class of "the rows of batch X" separates at precision 1.000 for a
        # reason that has nothing to do with the attestation being wrong. The
        # audit caught exactly that on the first draft. A settlement-level
        # class is smaller than MIN_CLASS_SIZE and is reported UNTESTABLE,
        # which is the honest answer rather than a flattering one.
        "d03_wrong_attestation": {
            "planted": bool(wrong_attestation), "table": "settlement_report",
            "members": [item["settlement_id"] for item in wrong_attestation],
            "detail": wrong_attestation,
            "reason": "" if wrong_attestation else
                      ("the PSP artefact is absent at this axis point, so "
                       "there is no attestation to corrupt"
                       if point.psp_attestation_absent
                       else "no attested batch had >=3 credit rows to corrupt")},
        # The class CHECKPOINT 0.1 says the corpus was missing: a settlement_id
        # written onto rows that are not the batch's composition, where the
        # arithmetic still closes. Settlement-level, like d03 and d04: the unit
        # of analysis has to match the unit the fact is about.
        "d11_false_settlement_id": {
            "planted": bool(false_compositions), "table": "recon",
            "members": [item["settlement_id"] for item in false_compositions],
            "detail": false_compositions,
            "reason": "" if false_compositions else
                      (false_reason or
                       "not planted at this axis point -- the original "
                       "fourteen datasets are not regenerated, and this class "
                       "ships only in corpus/datasets_v2/")},
        # Expressed at the SETTLEMENT level, like d03 and for the same reason.
        # Attestation is a property of a settlement, not of a row, and the rows
        # of one batch are not exchangeable observations -- they are one
        # observation repeated. Scoring at row level let a time-window
        # predicate reach 94% precision on 69% of the rows of three
        # consecutive batches, with a p-value that treated ~69 clustered rows
        # as independent. The unit of analysis has to match the unit the fact
        # is about.
        "d04_unattested_settlements": {
            "planted": point.attestation_coverage < 1,
            "table": "settlement_report",
            "reason": "" if point.attestation_coverage < 1 else
                      "attestation coverage is 100% at this axis point, so "
                      "there is nothing unattested -- absent by design, not "
                      "by failure",
            "members": sorted(b.settlement_id for b in batches
                              if b.settlement_id not in attested)},
        "d05_erp_orphan_invoices": {
            "planted": bool(orphans), "table": "erp", "members": orphans},
        "d06_payments_missing_from_erp": {
            "planted": bool(missing_erp), "table": "recon",
            "members": missing_erp},
        "d09_itc_at_risk": {
            "planted": bool(itc_at_risk), "table": "gstr2b",
            "members": [item["invoice_no"] for item in itc_at_risk]},
    })

    truth = OrderedDict(
        axis_point=point.name,
        seed=point.seed,
        generated_by="corpus/generator/build.py",
        contract="resolver_contract/RESOLVER_CONTRACT.md",
        spec="corpus/CORPUS_SPEC.md",
        warning="ISOLATED ANSWER KEY. No resolver may read this file.",
        axes={
            "A_pool_target": point.pool_target,
            "A_pool_sizes": [b.pool_size for b in batches],
            "A_pool_mean": round(sum(b.pool_size for b in batches)
                                 / max(len(batches), 1), 2),
            "B_attestation_coverage_target":
                "absent" if point.psp_attestation_absent
                else str(point.attestation_coverage),
            "B_attestation_coverage_achieved":
                f"{attested_count}/{len(batches)}",
            "C_selection_rule": point.selection_rule,
            "C_floor_fraction": str(point.floor_fraction),
        },
        merchant_gstin=merchant_gstin, gateway_gstin=gateway_gstin,
        gateway_fee_invoices=gateway_invoices,
        batches=batch_truth,
        determined_instances=sorted(determined),
        bank_lines=[{
            "line_index": line.line_index,
            "kind": line.kind,
            "true_settlement_id": (batches[line.payout_index].settlement_id
                                   if line.payout_index is not None else None),
            "attested": (line.payout_index is not None
                         and batches[line.payout_index].settlement_id in attested),
            "posting_lag_days": line.posting_lag_days,
            "reference_visible": line.reference_visible,
        } for line in bank_file.truth],
        attestation={
            "attested_settlement_ids": sorted(attested),
            "unattested_settlement_ids": sorted(
                b.settlement_id for b in batches
                if b.settlement_id not in attested),
            "wrong_attestations": wrong_attestation},
        settled_in=result.settled_in,
        unsettled_reason=result.unsettled_reason,
        netted_out=sorted(result.netted_out),
        roles=ledger.roles,
        planted_classes=planted,
        payments_missing_from_erp=missing_erp,
        erp_orphan_invoices=orphans,
        itc_at_risk=itc_at_risk,
        gst_rounding_residuals=residuals,
        bank_diagnostics={"reference_gaps": bank_file.reference_gaps,
                          "posting_lag_histogram": bank_file.lag_histogram},
        provenance=PROVENANCE,
    )

    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "recon_combined.json",
                OrderedDict(entity="collection", count=len(rows), items=rows))
    _write_json(out / "disputes.json",
                OrderedDict(entity="collection", count=len(ledger.disputes),
                            items=ledger.disputes))
    _write_csv(out / "bank_statement.csv", bank_file.rows)
    if point.psp_attestation_absent:
        # The artefact is ABSENT. Not an empty file with a header -- an empty
        # file would still assert "the PSP made no claims", which is a claim.
        (out / "settlement_report.csv").unlink(missing_ok=True)
    else:
        _write_csv(out / "settlement_report.csv", settlement_report)
    _write_csv(out / "erp_orders.csv", erp)
    _write_csv(out / "gstr2b.csv", gst_rows)
    _write_json(out / "ground_truth.json", truth)
    _write_hashes(out)
    (out / "GENERATION_REPORT.md").write_text(_report(point, truth, bank_file,
                                                      rows, erp, gst_rows))
    return {"axis_point": point.name, "rows": len(rows),
            "batches": len(batches), "bank_lines": len(bank_file.rows),
            "pool_mean": truth["axes"]["A_pool_mean"],
            "determined": len(determined)}


#: The provenance graph the oracle validates a resolver's independence claims
#: against. Two evidence kinds are independent iff they descend from disjoint
#: draws -- checkable only because we build the corpus, and the strongest
#: single argument for building one (contract sec 7).
PROVENANCE = {
    "recon_combined.json": {
        "party": "psp", "source_system": "psp_ledger",
        "drawn_from": "the ledger draw",
        "note": "settlement_id/settled/settled_at/settlement_utr are ONE "
                "assertion in four columns"},
    "settlement_report.csv": {
        "party": "psp", "source_system": "psp_settlement_report",
        "drawn_from": "the same simulation as recon_combined.json",
        "note": "NOT independent of the recon feed. Same party, second "
                "artefact. reported_reference is the PSP's CLAIM about the "
                "bank's reference, not the bank's assertion of it."},
    "bank_statement.csv": {
        "party": "bank", "source_system": "bank",
        "drawn_from": "an independent bank-side counter and lag distribution",
        "note": "built by corpus/generator/bank.py, which is never passed a "
                "settlement identifier. Shares ONLY amount, approximate date, "
                "and the remitter's name with the ledger -- see CORPUS_SPEC 5."},
    "erp_orders.csv": {
        "party": "merchant", "source_system": "merchant_erp",
        "drawn_from": "the ledger draw, plus an independent orphan draw",
        "note": "carries NO settlement reference, so it attests to a row's "
                "existence and never to batch membership"},
    "gstr2b.csv": {
        "party": "tax_authority", "source_system": "tax_authority",
        "drawn_from": "the fee columns, aggregated monthly"},
    "disputes.json": {
        "party": "issuer", "source_system": "dispute_record",
        "drawn_from": "the ledger draw"},
}


def _reference_range(bank_rows) -> tuple[int, int]:
    """The numeric band this file's real bank references occupy.

    An unissued reference drawn outside that band is separable by sorting,
    which is a leak about which settlements lost their attestation -- and
    which axis B exists to withhold.
    """
    digits = [int("".join(c for c in row["bank_reference"] if c.isdigit())[-6:])
              for row in bank_rows if row["bank_reference"]]
    return (min(digits), max(digits)) if digits else (0, 999_999)


def _pending_debits(rows, batch, batches, index):
    """Debits pending at a batch: created by then, not settled earlier.

    The simulator's `pool` is the eligible PAYMENTS only -- debits are applied,
    not selected -- so a closure register over the pool alone could not
    reproduce a payout that nets debits.
    """
    consumed: set[str] = set()
    for earlier in batches[:index]:
        consumed.update(earlier.credit_ids)
        consumed.update(earlier.debit_ids)
    return [row["entity_id"] for row in rows
            if row["type"] in ("refund", "adjustment")
            and row["entity_id"] not in consumed
            and row["created_at"] <= batch.formed_at]


def _pool_at(rows, batch, batches, index, config):
    """The eligible pool at a batch, as signed net contributions.

    Reconstructed from the emitted rows using only blocking rules a solver
    could also apply -- so the closure register answers the same question a
    solver faces, and any difference in answer is a difference in method.
    """
    consumed: set[str] = set()
    for earlier in batches[:index]:
        consumed.update(earlier.credit_ids)
        consumed.update(earlier.debit_ids)
    when = batch.formed_at
    pool: list[tuple[str, int]] = []
    for row in rows:
        if row["entity_id"] in consumed:
            continue
        if row["type"] == "payment" and row["fee"] is None:
            continue
        if row["on_hold"] or row["created_at"] > when:
            continue
        if row["type"] == "payment":
            eligible = _add_working_days(row["created_at"],
                                         config.settlement_delay_working_days,
                                         config.cutoff_hour)
            if eligible > when:
                continue
        pool.append((row["entity_id"], row["credit"] - row["debit"]))
    return pool


def _add_working_days(timestamp: int, days: int, cutoff_hour: int) -> int:
    moment = datetime.fromtimestamp(timestamp, IST)
    remaining = days
    while remaining > 0:
        moment += timedelta(days=1)
        if moment.weekday() < 5:
            remaining -= 1
    return int(moment.replace(hour=cutoff_hour, minute=0, second=0,
                              microsecond=0).timestamp())


def _write_hashes(out: Path) -> None:
    lines = []
    for name in FROZEN_FILES:
        path = out / name
        if path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {name}")
    (out / "DATASET_HASHES.txt").write_text("\n".join(lines) + "\n")


def _report(point, truth, bank_file, rows, erp, gst_rows) -> str:
    closure_states = Counter(b["closure"]["recoverable"]
                             for b in truth["batches"])
    types = Counter(row["type"] for row in rows)
    truth_in = Counter(str(b["truth_in_closure"]) for b in truth["batches"])
    planted = truth["planted_classes"]
    not_planted = [(name, spec.get("reason", "")) for name, spec
                   in sorted(planted.items()) if not spec.get("planted")]
    lines = [
        f"# GENERATION REPORT -- {point.name}", "",
        point.note or "", "",
        "| axis | target | achieved |", "|---|---|---|",
        f"| A pool size | {point.pool_target} | mean "
        f"{truth['axes']['A_pool_mean']}, sizes "
        f"{truth['axes']['A_pool_sizes']} |",
        f"| B attestation coverage | {point.attestation_coverage} | "
        f"{truth['axes']['B_attestation_coverage_achieved']} |",
        f"| C selection rule | {point.selection_rule} | "
        f"{point.selection_rule} (phi={point.floor_fraction}) |",
        "",
        f"seed `{point.seed}`, committed before generation.", "",
        "## Volume", "",
        f"- recon rows: {len(rows)}  {dict(types)}",
        f"- settlements: {len(truth['batches'])}",
        f"- bank lines: {len(bank_file.rows)} "
        f"({sum(1 for l in truth['bank_lines'] if l['kind'] != 'settlement')} "
        "of them NOT ours)",
        f"- ERP invoices: {len(erp)}; GSTR-2B lines: {len(gst_rows)}",
        "",
        "## Closure, measured with NO objective", "",
        "The frozen key records subsets tying at the MAXIMUM. This records",
        "every subset that closes, under no objective at all -- which is what",
        "makes D1 measurable rather than latent.", "",
        f"- {dict(closure_states)}",
        f"- true composition closes arithmetically: "
        f"{sum(1 for b in truth['batches'] if b['composition_closes'])}"
        f"/{len(truth['batches'])} (asserted at generation, not merely reported)",
        f"- truth present in the closure register: {dict(truth_in)}",
        f"- **determined instances** (unique closure, complete enumeration, "
        f"attested, attestation correct): {len(truth['determined_instances'])}",
        "  These are the lines on which `Unresolved` is a DEFECT, gated at",
        "  zero by the resolver contract sec 6.1. Without them every guarantee",
        "  in the contract is satisfiable by answering nothing.", "",
        "## Bank independence", "",
        f"- posting lag histogram (days): {bank_file.lag_histogram}",
        f"- reference gaps: min {min(bank_file.reference_gaps)}, "
        f"max {max(bank_file.reference_gaps)} "
        f"(a dense sequence would be a counter minted for this file)",
        "",
        "## Classes recorded as NOT planted", "",
    ]
    if not_planted:
        lines += [f"- `{name}` -- {reason or 'target unreachable by selection'}"
                  for name, reason in not_planted]
    else:
        lines.append("- none")
    lines += [
        "",
        "A class that could not be achieved by SELECTING organic rows is",
        "recorded here as `planted: false` with its reason. No row is ever",
        "minted to force a target -- that is defect D5, and it leaked in the",
        "`amount` column before anyone read a description string.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs="?", help="axis point to build")
    parser.add_argument("--all", action="store_true",
                        help="the original fourteen. Regenerating them is a "
                             "freeze violation unless nothing changed.")
    parser.add_argument("--absence", action="store_true",
                        help="the two PSP-absence points")
    parser.add_argument("--v2", action="store_true",
                        help="corpus/datasets_v2/: the same axis points at new "
                             "seeds, each with one FALSE settlement_id")
    parser.add_argument("--list", action="store_true")
    arguments = parser.parse_args()

    if arguments.list:
        for point in ALL_POINTS:
            coverage = ("absent" if point.psp_attestation_absent
                        else str(point.attestation_coverage))
            print(f"{point.family:<13} {point.name:<22} "
                  f"pool~{point.pool_target:<3} cov={coverage:<7}"
                  f"{point.selection_rule:<15} seed={point.seed}"
                  f"{'  +false_settlement_id' if point.false_compositions else ''}")
        return 0

    targets: list[AxisPoint] = []
    if arguments.all:
        targets += AXIS_POINTS
    if arguments.absence:
        targets += ABSENCE_POINTS
    if arguments.v2:
        targets += V2_POINTS
    if arguments.name:
        targets += [V2_BY_NAME[arguments.name] if arguments.v2
                    else AXIS_BY_NAME[arguments.name]]
    if not targets:
        parser.error("name one axis point, or pass --all / --absence / --v2")
    for point in targets:
        summary = build(point)
        print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
