"""`pool_at` must be a SUPERSET of the true composition. `DECISIONS.md` §44.

The module promises this in its own docstring — it "errs LARGE where the rules
are uncertain" — and an `on_hold` filter quietly broke it, because `on_hold` is
a current-state snapshot and the pool is built as at a past `value_date`.

Two tests, and they are not equally strong. Read the note on the second one:
it does not currently discriminate, and saying so is the point.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from resolver.eligibility import eligible_at, end_of_day, pool_at

ROOT = Path(__file__).resolve().parents[2]


def datasets():
    for family in ("datasets", "datasets_v2"):
        base = ROOT / "corpus" / family
        for slug in sorted(os.listdir(base)):
            if (base / slug).is_dir():
                yield f"{family}/{slug}"


# --------------------------------------------------------------------------
# the discriminating test: synthetic, and it FAILS if the filter returns
# --------------------------------------------------------------------------


def test_a_held_row_is_still_in_the_pool():
    """THE test for F1.

    A row held *now* may not have been held at `value_date`, and the Razorpay
    dispute entity publishes no resolution timestamp, so the resolver cannot
    tell which (`DECISIONS.md` §44.5). The safe direction is to keep it: a pool
    that is too large makes closure non-unique, which is LOUD; a pool that is
    too small makes the truth unreachable, which is SILENT.
    """
    created = 1_800_000_000
    row = {"entity_id": "pay_held", "type": "payment", "credit": 100_000,
           "debit": 0, "amount": 100_000, "created_at": created,
           "on_hold": True, "payment_id": None}
    day = __import__("datetime").datetime.fromtimestamp(
        eligible_at(created) + 86_400,
        __import__("datetime").timezone(
            __import__("datetime").timedelta(hours=5, minutes=30))).date()
    assert end_of_day(day) >= eligible_at(created)
    ids = [row_id for row_id, _ in pool_at([row], day, set())]
    assert ids == ["pay_held"], (
        "a held row was dropped from the pool -- the on_hold filter is back, "
        "and with it the silent failure mode F1 describes "
        "(resolver/eligibility.py, DECISIONS.md 44)")


def test_the_other_exclusions_still_apply():
    """Removing one filter must not remove the rest."""
    created = 1_800_000_000
    day = __import__("datetime").datetime.fromtimestamp(
        eligible_at(created) + 86_400,
        __import__("datetime").timezone(
            __import__("datetime").timedelta(hours=5, minutes=30))).date()

    def one(**over):
        row = {"entity_id": "x", "type": "payment", "credit": 100_000,
               "debit": 0, "amount": 100_000, "created_at": created,
               "on_hold": False, "payment_id": None}
        row.update(over)
        return [rid for rid, _ in pool_at([row], day, set())]

    assert one(credit=0) == []                       # never captured
    assert one(created_at=end_of_day(day) + 1) == []  # created after posting
    assert one(credit=0, debit=0, type="adjustment") == []   # zero net
    assert [rid for rid, _ in pool_at(
        [{"entity_id": "x", "type": "payment", "credit": 100_000, "debit": 0,
          "amount": 100_000, "created_at": created, "on_hold": False,
          "payment_id": None}], day, {"x"})] == []   # already consumed


# --------------------------------------------------------------------------
# the corpus-wide invariant: weaker, and honest about being weaker
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(datasets()))
def test_the_pool_is_a_superset_of_the_true_composition(name):
    """The invariant `pool_at`'s docstring promises, over real data.

    HONEST LIMITATION: this test passes with the `on_hold` filter present as
    well as absent, because 0 rows carrying `on_hold` appear in any true
    composition across all 30 datasets. It did NOT catch F1 and would not have.
    It is a regression guard against future data that does exercise the case,
    and `test_a_held_row_is_still_in_the_pool` is the one that discriminates.

    Recording that distinction matters more than the assertion: a suite that
    passes for the wrong reason is how F1 shipped in the first place.
    """
    directory = ROOT / "corpus" / name
    rows = json.loads((directory / "recon_combined.json").read_text())["items"]
    truth = json.loads((directory / "ground_truth.json").read_text())
    bank = {int(line["line_index"]): line for line in truth["bank_lines"]}
    import csv
    from datetime import date
    value_date = {}
    with open(directory / "bank_statement.csv") as handle:
        for index, entry in enumerate(csv.DictReader(handle)):
            value_date[index] = date.fromisoformat(entry["value_date"])

    for batch in truth["batches"]:
        index = batch.get("bank_line_index")
        if index is None or index not in value_date:
            continue
        pool = {row_id for row_id, _ in pool_at(rows, value_date[index], set())}
        missing = sorted(set(batch["composition"]) - pool)
        assert not missing, (
            f"{name} bank[{index}] settlement {batch['settlement_id']}: "
            f"{len(missing)} row(s) of the TRUE composition are not in the "
            f"pool, so no enumeration can reach it: {missing[:4]}")


# --------------------------------------------------------------------------
# D14: the resolver's horizon is not the answer key's, and the ordering is
# what makes one reason sound. Nothing guarded that until now.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(datasets()))
def test_the_resolver_horizon_is_never_earlier_than_the_answer_keys(name):
    """D14, closed.

    `OpenBreak(TIMING_DIFFERENCE)` is sound because `eligible_at > H_resolver`
    implies `eligible_at > H_truth` — the test is STRICTLY STRONGER than the
    one the answer key applies, so it can miss but never false-positive. That
    argument holds only while

        H_resolver (last bank value_date) >= H_truth (last batch formed_at)

    and nothing checked it. If a dataset ever posts its last bank credit
    BEFORE the last batch forms, the implication inverts and the reason starts
    making claims it cannot support (`DECISIONS.md` §44, row 4 of the
    inventory).
    """
    directory = ROOT / "corpus" / name
    truth = json.loads((directory / "ground_truth.json").read_text())
    import csv
    from datetime import date
    with open(directory / "bank_statement.csv") as handle:
        last_value_date = max(date.fromisoformat(entry["value_date"])
                              for entry in csv.DictReader(handle))
    resolver_horizon = end_of_day(last_value_date)
    truth_horizon = max(batch["formed_at"] for batch in truth["batches"])
    assert resolver_horizon >= truth_horizon, (
        f"{name}: the resolver's horizon {resolver_horizon} is EARLIER than "
        f"the answer key's {truth_horizon}. TIMING_DIFFERENCE's soundness "
        "argument inverts and the reason must be withdrawn before this "
        "dataset is scored (DECISIONS.md 44)")
