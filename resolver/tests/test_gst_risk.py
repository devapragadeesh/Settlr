"""GST evidence reaches this resolver, and it may only ever ANNOTATE.

`resolver_contract/types.py` restricts `EvidenceKind.GST_DOCUMENT` to
`Attests.ROW_EXISTENCE`. A tax return can say an invoice exists; it can say
nothing whatever about which recon rows composed a bank credit. So the whole of
this capability is confined to `OpenBreak` -- rows the resolver has ALREADY
failed to place, decided before `dispositions()` is called at all.

That is a structural claim, and prose is not evidence for it. The first two
tests check it mechanically:

* run the resolver with and without `gstr2b.csv` and diff every outcome that is
  not an `OpenBreak`. If GST data could influence a composition, this fails.
  That diff runs against a SMALL dataset built in this file rather than against
  a corpus dataset, for a reason that has nothing to do with GST: see
  `DECISIONS.md` sec 58 and the comment on the test itself;
* walk every warrant on every composition-bearing outcome across every GST
  dataset and assert `GST_DOCUMENT` never appears in one.

The third test exists for a different reason. `resolver/breaks.py` REIMPLEMENTS
the gateway-GSTIN identification and the three statutory checks rather than
importing `matching/stage4_exceptions.py`, because `test_isolation.py` forbids
that import outright. Two independent implementations of one rule can drift,
and the mitigation for accepting that risk is this test: the two must agree on
every GST dataset in the corpus. It is mandatory, not a nicety.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from resolver.breaks import (
    GROUND_37A, GROUND_ABSENT, GROUND_NO_IRN, _accrues_input_tax,
    _itc_risk_months, _month, dispositions, gateway_gstin,
)
from resolver.eligibility import IST
from resolver.loaders import BankLine, Dataset, Gstr2bLine, load
from resolver.resolve import resolve
from resolver_contract.types import EvidenceKind, OpenBreak

ROOT = Path(__file__).resolve().parents[2]
GST_ROOT = ROOT / "corpus" / "datasets_gst"
GST_DATASETS = sorted(p for p in GST_ROOT.iterdir() if p.is_dir())
SPINE = GST_ROOT / "A20_B100_Cmax_gst"

GATEWAY = "29AAAAA0000A1Z5"


def _at(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, 12, 0, tzinfo=IST).timestamp())


def test_the_corpus_actually_has_gst_datasets():
    """A parametrised suite over an empty directory passes silently."""
    assert GST_DATASETS, f"no dataset directories under {GST_ROOT}"


@pytest.fixture(scope="module")
def gst_outputs():
    return {path.name: resolve(load(path)) for path in GST_DATASETS}


# --------------------------------------------------------------------------
# 1. the loader is a no-op for everything that carries a composition
# --------------------------------------------------------------------------


def _rupees(paise: int) -> str:
    return f"{paise // 100}.{paise % 100:02d}"


def _settled_payment(entity_id: str, amount: int, fee: int, tax: int,
                     created: int, settled_at: int, settlement_id: str,
                     utr: str | None) -> dict:
    """One recon row, in the shape `resolver/loaders.py` actually reads."""
    return {"entity_id": entity_id, "type": "payment", "debit": 0,
            "credit": amount - fee, "amount": amount, "currency": "INR",
            "fee": fee, "tax": tax, "on_hold": False, "settled": True,
            "created_at": created, "settled_at": settled_at,
            "settlement_id": settlement_id, "posted_at": None,
            "credit_type": "default", "description": "Order payment",
            "notes": [], "payment_id": None, "settlement_utr": utr,
            "order_id": None, "dispute_id": None}


#: Three months. JUNE settles and is reported, so its bank credit carries a
#: composition. AUGUST settles with no `settlement_report` row, so its credit
#: is placed without a PSP attestation. JULY settles per the ledger but no bank
#: credit ever arrives, so its rows survive to `dispositions()` as OpenBreaks
#: -- and August's fee accrual has no 2B line behind it either, which is what
#: puts July's month at ITC risk and gives the annotation something to say.
_JUNE = [_settled_payment(f"pay_june_{i}", 100_000 + i * 1_000,
                          2_000 + i * 100, 300 + i * 10,
                          _at(2027, 6, 1 + i), _at(2027, 6, 20),
                          "setl_june", "REFJUNE") for i in range(4)]
_JULY = [_settled_payment(f"pay_july_{i}", 200_000 + i * 1_000,
                          5_000 + i * 100, 700 + i * 10,
                          _at(2027, 7, 1 + i), _at(2027, 7, 20),
                          "setl_july", "REFJULY") for i in range(3)]
_AUGUST = [_settled_payment(f"pay_aug_{i}", 300_000 + i * 1_000,
                            7_000 + i * 100, 900 + i * 10,
                            _at(2027, 8, 1 + i), _at(2027, 8, 20),
                            "setl_aug", None) for i in range(3)]

_JUNE_CREDIT = sum(row["credit"] for row in _JUNE)
_AUGUST_CREDIT = sum(row["credit"] for row in _AUGUST)
#: The gateway's June invoice, reconciling to the fee net of its own GST --
#: `resolver/breaks.py::_fee_accrual`'s definition, which is how
#: `gateway_gstin` finds the supplier at all.
_JUNE_TAXABLE = sum(row["fee"] - row["tax"] for row in _JUNE)


def _write_small_gst_dataset(directory: Path, *, with_gst: bool) -> Path:
    """A seven-row dataset directory, written from the constants above.

    Deliberately NOT a copy of a corpus dataset. See
    `test_removing_the_gst_feed_changes_nothing_but_the_annotation` for why the
    size is load-bearing. `ground_truth.json` is not written at all -- nothing
    under `resolver/` may open it, and the surest way to keep that true is for
    it not to exist.
    """
    directory.mkdir(parents=True)
    rows = _JUNE + _JULY + _AUGUST
    (directory / "recon_combined.json").write_text(json.dumps(
        {"entity": "collection", "count": len(rows), "items": rows}, indent=1))

    with (directory / "bank_statement.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["bank_reference", "value_date", "narration", "amount"])
        writer.writerow(["REFJUNE", "2027-06-20", "NEFT CR REFJUNE",
                         _rupees(_JUNE_CREDIT)])
        writer.writerow(["REFAUG", "2027-08-20", "NEFT CR REFAUG",
                         _rupees(_AUGUST_CREDIT)])

    with (directory / "settlement_report.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["settlement_id", "reported_reference",
                         "reported_amount", "initiated_at", "status"])
        writer.writerow(["setl_june", "REFJUNE", _rupees(_JUNE_CREDIT),
                         "2027-06-20", "processed"])

    if with_gst:
        with (directory / "gstr2b.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "gstin", "invoice_no", "invoice_date", "taxable_value", "igst",
                "cgst", "sgst", "irn", "irn_generated_at",
                "gstr1_filing_period", "supplier_gstr3b_filed",
                "itc_availability"])
            writer.writerow([GATEWAY, "INV/1", "2027-06-30",
                             _rupees(_JUNE_TAXABLE), "0.00", "0.00", "0.00",
                             "irn-1", "2027-06-30T09:15:00", "2027-06", "Y",
                             "Yes"])
    assert (directory / "gstr2b.csv").exists() is with_gst
    return directory


def test_removing_the_gst_feed_changes_nothing_but_the_annotation(tmp_path):
    """The mechanical proof that GST evidence cannot touch a composition.

    WHY THIS RUNS ON A SEVEN-ROW FIXTURE AND NOT ON THE SPINE -- read
    `DECISIONS.md` sec 58 before changing it back.

    This test compares two `resolve()` runs. `resolve()` is NOT reproducible
    run-to-run on a dataset large enough for a closure enumeration to hit its
    time budget: `resolver/enumerate_closures.py` budgets in WALL-CLOCK seconds
    (`max_time_in_seconds`, default 10.0) rather than in OR-Tools'
    deterministic time, so a truncated search stops at a different point on
    every run and the same bank line can come back with a different
    composition. That is sec 39's / sec 49's defect class, unfixed in this
    component, and it has nothing whatever to do with GST -- but it made this
    test fail at bank index 56 on one run and 58 on another when it ran against
    `A20_B100_Cmax_gst`.

    Raising `time_budget` does NOT fix it and was measured, not assumed: at
    60.0 one pool in that dataset still exhausts the budget without proving
    completeness (sec 58's table). The fixture below instead keeps the whole
    proof outside the truncating regime -- four closure enumerations, all four
    reported `optimal`, whole test well under a second -- so it is not hostage
    to a defect it does not test. Do NOT replace it with a corpus dataset, and
    do NOT "simplify" it by deleting the fixture in favour of `SPINE`; the
    flake comes straight back and looks like a GST bug.

    The dataset name is identical in both copies so that `ResolverOutput.
    dataset` is not a spurious difference -- if the two runs differ, they must
    differ for a REASON, not because a temporary directory has another name.
    """
    with_gst = resolve(load(_write_small_gst_dataset(
        tmp_path / "with" / "fixture", with_gst=True)))
    without_gst = resolve(load(_write_small_gst_dataset(
        tmp_path / "without" / "fixture", with_gst=False)))

    assert without_gst.dataset == with_gst.dataset
    # Every per-bank-line outcome -- Verified, Ambiguous, Reconstructed,
    # AttestationDiscrepancy, Unresolved -- identical, value and repr.
    assert without_gst.line_outcomes == with_gst.line_outcomes
    assert repr(without_gst.line_outcomes) == repr(with_gst.line_outcomes)

    # And every disposition too, except for the annotation itself.
    a = [u for u in with_gst.unmatched if not isinstance(u, OpenBreak)]
    b = [u for u in without_gst.unmatched if not isinstance(u, OpenBreak)]
    assert a == b and repr(a) == repr(b)

    breaks_with = [u for u in with_gst.unmatched if isinstance(u, OpenBreak)]
    breaks_without = [u for u in without_gst.unmatched
                      if isinstance(u, OpenBreak)]
    assert len(breaks_with) == len(breaks_without)
    for one, other in zip(breaks_with, breaks_without):
        assert one.row_ids == other.row_ids
        assert one.reason is other.reason
        assert one.age_days == other.age_days
        assert one.first_seen == other.first_seen
        assert one.caused_by == other.caused_by
        assert one.provable_within_window == other.provable_within_window
        # The ONLY permitted difference.
        assert other.itc_risk == frozenset()
        assert other.itc_risk_grounds == ()

    # Non-vacuity, in the same test rather than a neighbouring one: if the
    # fixture stopped producing a composition or stopped flagging anything,
    # every assertion above would pass by comparing nothing against nothing.
    assert with_gst.line_outcomes, "the fixture produced no bank-line outcome"
    assert any(getattr(o, "composition", None) for o in with_gst.line_outcomes)
    assert any(b.itc_risk for b in breaks_with), (
        "no OpenBreak carries an ITC-risk flag; the diff above is comparing a "
        "capability against itself switched off")


def test_the_small_fixture_stays_out_of_the_truncating_regime(tmp_path):
    """The guard on `DECISIONS.md` sec 58's workaround.

    The test above is only sound while the fixture's closure enumerations all
    COMPLETE -- an enumeration cut off by the wall-clock budget is not
    reproducible, so a fixture grown large enough to truncate would reintroduce
    the flake silently and it would once again look like a GST bug. Resolving
    the same directory twice and requiring equality states that condition
    directly: this test fails first, and says what is wrong.
    """
    directory = _write_small_gst_dataset(tmp_path / "fixture", with_gst=True)
    first = resolve(load(directory))
    second = resolve(load(directory))
    assert first.line_outcomes == second.line_outcomes
    assert repr(first.line_outcomes) == repr(second.line_outcomes)


def test_the_spine_flags_nothing_because_it_has_nothing_to_flag(gst_outputs):
    """The spine's at-risk-and-open population is EMPTY. Read sec 60 and sec 61.

    This assertion was inverted, and the inversion is the point. It used to
    read "the spine actually flags something", and it passed -- on four rows
    that had **never settled**, which sec 60 then measured as four false
    positives and a precision of 0.0. Sec 61 gates the flag on the row's own
    `_accrues_input_tax`, and the spine now correctly flags nothing.

    So this test asserts the emptiness together with its REASON, because
    "flags nothing" is also what a flag wired to a constant `False` would
    produce, and the two must not be indistinguishable. Of the 22 rows sitting
    in some `OpenBreak`, the four that accrued input tax settled in a month
    carrying no ground, and the eighteen in at-risk months accrued none. There
    is no row here that is both, so there is nothing correct to flag.

    Non-vacuity of the sec 59 no-op proof does NOT depend on this dataset: it
    is asserted inside
    `test_removing_the_gst_feed_changes_nothing_but_the_annotation` against
    its own fixture, which does flag, and the gate's positive and negative
    branches are exercised by
    `test_a_row_that_never_settled_is_not_flagged_by_its_break_mate` below.
    """
    output = gst_outputs[SPINE.name]
    dataset = load(SPINE)
    at_risk = _itc_risk_months(dataset)
    rows = {row["entity_id"]: row for row in dataset.rows}
    assert at_risk, "the spine carries no at-risk month at all; this test " \
                    "would then be asserting nothing about the row-level gate"

    open_rows = [row_id for outcome in output.unmatched
                 if isinstance(outcome, OpenBreak) for row_id in outcome.row_ids]
    assert open_rows, "no row is open; nothing was flaggable in the first place"

    accruing = [r for r in open_rows if _accrues_input_tax(rows[r])]
    in_bad_month = [r for r in open_rows if _month(rows[r]) in at_risk]
    # Both halves non-empty: the emptiness below is an intersection that is
    # empty, not an operand that is.
    assert accruing and in_bad_month
    assert not (set(accruing) & set(in_bad_month))

    flagged = [b for b in output.unmatched
               if isinstance(b, OpenBreak) and b.itc_risk]
    assert not flagged, (
        "rows flagged where no open row both accrued input tax and sits in an "
        f"at-risk month: {[sorted(b.itc_risk) for b in flagged]}")


def test_a_row_that_never_settled_is_not_flagged_by_its_break_mate():
    """Sec 61's fix, on the smallest fixture that can state it.

    Two payments, identical in every field the break-grouping key reads, so
    they land in ONE `OpenBreak` -- same reason, same `first_seen`, same age.
    Both sit in a month carrying a genuine `gstr2b_no_irn` ground. They differ
    in one thing: one settled per the PSP's own ledger and the other never
    did, so only the first ever generated a fee for the gateway to invoice and
    charge GST on.

    Before sec 61 the flag was `_month(row) in at_risk` alone, and BOTH rows
    were flagged -- the second inheriting an exposure it could not have, from
    the month it merely shared. Exactly one row must come back flagged, and it
    must be the settled one; asserting the count alone would pass if the wrong
    row were picked.
    """
    settled = _fee_payment("pay_settled", SETTLED)
    never = _fee_payment("pay_never", SETTLED) | {"settled_at": None}
    dataset = Dataset(
        name="fixture", rows=[settled, never],
        bank=[BankLine(index=0, reference="REF", value_date=date(2027, 6, 30),
                       narration="NEFT CR REF", amount_paise=99_000)],
        gstr2b=[_line(PERIOD, irn="")])

    assert _itc_risk_months(dataset) == {PERIOD: (GROUND_NO_IRN,)}
    assert _accrues_input_tax(settled) and not _accrues_input_tax(never)

    breaks = [d for d in dispositions(dataset, consumed=set(), blocked={})
              if isinstance(d, OpenBreak)]
    # The premise: one break holding both rows. If a future grouping key splits
    # them the test still checks the right thing, but it stops checking THIS.
    assert len(breaks) == 1 and set(breaks[0].row_ids) == {"pay_settled",
                                                           "pay_never"}
    assert breaks[0].itc_risk == frozenset({"pay_settled"})
    assert breaks[0].itc_risk_grounds == (GROUND_NO_IRN,)


# --------------------------------------------------------------------------
# 2. GST_DOCUMENT never appears in a warrant that licenses a composition
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", [p.name for p in GST_DATASETS])
def test_gst_evidence_never_warrants_a_composition(gst_outputs, name):
    """Contract sec 3: `GST_DOCUMENT` attests to ROW EXISTENCE.

    Checked over EVERY outcome carrying a warrant rather than a named list of
    types, so a future outcome type is covered the day it is added rather than
    the day someone remembers to extend this list.
    """
    output = gst_outputs[name]
    for outcome in output.line_outcomes:
        warrant = getattr(outcome, "warrant", None)
        if warrant is None:
            continue
        assert EvidenceKind.GST_DOCUMENT not in warrant.kinds, (
            f"{name} bank[{outcome.bank_index}] "
            f"({type(outcome).__name__}) rests on a tax document")
    for disposition in output.unmatched:
        warrant = getattr(disposition, "warrant", None)
        if warrant is None:
            continue
        assert EvidenceKind.GST_DOCUMENT not in warrant.kinds, (
            f"{name} {type(disposition).__name__} rests on a tax document")


@pytest.mark.parametrize("name", [p.name for p in GST_DATASETS])
def test_every_flag_names_rows_the_break_contains(gst_outputs, name):
    """`itc_risk` is a SUBSET of `row_ids`, and never a bare accusation."""
    for outcome in gst_outputs[name].unmatched:
        if not isinstance(outcome, OpenBreak):
            continue
        assert outcome.itc_risk <= set(outcome.row_ids)
        assert bool(outcome.itc_risk) == bool(outcome.itc_risk_grounds)
        assert set(outcome.itc_risk_grounds) <= {
            GROUND_ABSENT, GROUND_NO_IRN, GROUND_37A}


# --------------------------------------------------------------------------
# 3. the mandatory cross-check against the frozen reference implementation
# --------------------------------------------------------------------------


def _matching_dataset(directory: Path):
    """The frozen cascade's own view of a corpus dataset's 2B feed.

    `matching.loaders.load` cannot read a corpus directory -- the bank file
    uses different column names -- so the reference `Dataset` is built here
    from the same CSV, with the frozen package's OWN parser and OWN line type.
    The point of the cross-check is that the reference is genuinely the
    reference; borrowing this resolver's parsing would make the test check
    nothing.
    """
    from matching.loaders import Dataset as MatchingDataset, Gstr2bLine as Ref
    from matching.loaders import paise as ref_paise
    import json

    rows = json.loads((directory / "recon_combined.json").read_text())["items"]
    lines = []
    with (directory / "gstr2b.csv").open(newline="") as handle:
        for line in csv.DictReader(handle):
            lines.append(Ref(
                gstin=line["gstin"],
                invoice_no=line["invoice_no"],
                invoice_date=date.fromisoformat(line["invoice_date"]),
                taxable_value=ref_paise(line["taxable_value"]),
                igst=ref_paise(line["igst"]),
                cgst=ref_paise(line["cgst"]),
                sgst=ref_paise(line["sgst"]),
                irn=line["irn"],
                irn_generated_at=line["irn_generated_at"],
                gstr1_filing_period=line["gstr1_filing_period"],
                supplier_gstr3b_filed=line["supplier_gstr3b_filed"],
                itc_availability=line["itc_availability"]))
    return MatchingDataset(rows=rows, bank=[], erp=[], gstr2b=lines,
                           disputes=[])


@pytest.mark.parametrize("name", [p.name for p in GST_DATASETS])
def test_gateway_identification_agrees_with_the_frozen_reference(name):
    """The mitigation for the accepted duplication in `resolver/breaks.py`.

    `matching/` is imported HERE and only here: `test_isolation.py` forbids it
    inside `resolver/` sources, and this file is a test, not a resolver module.
    A disagreement is not to be papered over by copying the reference
    algorithm -- that would defeat the independence the duplication exists to
    protect. It is to be investigated.
    """
    from matching.stage4_exceptions import identify_supplier, monthly_fee_accrual

    directory = GST_ROOT / name
    reference_dataset = _matching_dataset(directory)
    reference = identify_supplier(reference_dataset,
                                  monthly_fee_accrual(reference_dataset))
    assert gateway_gstin(load(directory)) == reference, (
        f"{name}: the resolver and the frozen cascade disagree about which "
        "GSTIN is the gateway")


@pytest.mark.parametrize("name", [p.name for p in GST_DATASETS])
def test_a_gateway_is_actually_found(name):
    """Two implementations that both return `None` agree about nothing."""
    assert gateway_gstin(load(GST_ROOT / name)) is not None


# --------------------------------------------------------------------------
# 4. `_itc_risk_months` against fixtures small enough to reason about
#    (`GATEWAY` and `_at` are defined at the top of this file, shared with the
#     dataset fixture in section 1)
# --------------------------------------------------------------------------


def _fee_payment(entity_id: str, settled: int, fee: int = 1_000,
                 tax: int = 100) -> dict:
    """A settled payment that accrued a gateway fee with GST on it."""
    return {"entity_id": entity_id, "type": "payment", "amount": 100_000,
            "credit": 100_000 - fee, "debit": 0, "fee": fee, "tax": tax,
            "created_at": settled, "settled_at": settled, "payment_id": None}


def _line(period: str, *, gstin: str = GATEWAY, taxable: int = 900,
          irn: str = "abc123", filed: str = "Y",
          invoice_no: str = "INV/1") -> Gstr2bLine:
    return Gstr2bLine(
        gstin=gstin, invoice_no=invoice_no,
        invoice_date=date.fromisoformat(f"{period}-28"),
        taxable_value=taxable, igst=0, cgst=50, sgst=50, irn=irn,
        irn_generated_at="", gstr1_filing_period=period,
        supplier_gstr3b_filed=filed, itc_availability="Yes")


def _dataset(rows, lines) -> Dataset:
    return Dataset(name="fixture", rows=rows, bank=[], gstr2b=list(lines))


PERIOD = "2027-06"
SETTLED = _at(2027, 6, 15)


def test_a_clean_month_carries_no_ground():
    dataset = _dataset([_fee_payment("pay_1", SETTLED)], [_line(PERIOD)])
    assert gateway_gstin(dataset) == GATEWAY
    assert _itc_risk_months(dataset) == {}


def test_an_accrued_month_with_no_2b_line_is_absent():
    """The gateway must still be identifiable from ANOTHER month, or there is
    no supplier to find and the absence is unattributable."""
    rows = [_fee_payment("pay_1", SETTLED),
            _fee_payment("pay_2", _at(2027, 7, 15))]
    dataset = _dataset(rows, [_line(PERIOD)])
    assert _itc_risk_months(dataset) == {"2027-07": (GROUND_ABSENT,)}


def test_a_line_with_no_irn_is_flagged_in_its_filing_period():
    dataset = _dataset([_fee_payment("pay_1", SETTLED)],
                       [_line(PERIOD, irn="   ")])
    assert _itc_risk_months(dataset) == {PERIOD: (GROUND_NO_IRN,)}


def test_an_unfiled_gstr3b_is_a_37A_exposure():
    dataset = _dataset([_fee_payment("pay_1", SETTLED)],
                       [_line(PERIOD, filed="n")])
    assert _itc_risk_months(dataset) == {PERIOD: (GROUND_37A,)}


def test_two_grounds_on_one_invoice_compound_rather_than_shadow():
    """The reference implementation raises both, and so must this: an `elif`
    here would report the missing IRN and silently drop the 37A exposure,
    understating the amount at risk."""
    dataset = _dataset([_fee_payment("pay_1", SETTLED)],
                       [_line(PERIOD, irn="", filed="N")])
    assert _itc_risk_months(dataset) == {
        PERIOD: (GROUND_37A, GROUND_NO_IRN)}


def test_another_suppliers_defects_are_not_the_gateways():
    """2B carries every supplier the merchant bought from. Flagging a
    stationery vendor's unfiled return as a settlement finding would be a
    false positive with a plausible-looking citation attached."""
    dataset = _dataset(
        [_fee_payment("pay_1", SETTLED)],
        [_line(PERIOD),
         _line(PERIOD, gstin="29BBBBB1111B1Z5", taxable=7_777, irn="",
               filed="N", invoice_no="INV/2")])
    assert gateway_gstin(dataset) == GATEWAY
    assert _itc_risk_months(dataset) == {}


def test_no_2b_at_all_yields_no_finding_rather_than_a_universal_one():
    """Absence of the feed is absence of evidence. A resolver that read it as
    "every month is at risk" would flag hardest exactly where it knows least."""
    dataset = _dataset([_fee_payment("pay_1", SETTLED)], [])
    assert gateway_gstin(dataset) is None
    assert _itc_risk_months(dataset) == {}


def test_a_fee_with_no_gst_on_it_accrues_no_taxable_value():
    """There is no input tax to claim on it, so it cannot make a month at
    risk of losing one."""
    row = _fee_payment("pay_1", SETTLED, tax=0)
    dataset = _dataset([row, _fee_payment("pay_2", SETTLED)], [_line(PERIOD)])
    assert _itc_risk_months(dataset) == {}
