"""No ledger field is recoverable from the corpus bank file. Defect D4.

## A test that cannot detect the known defect is not a test

Every assertion here is run twice: once over each corpus dataset, where it must
PASS, and once over `engine/data/bank_statement.csv`, where it must **FAIL**.
The frozen file is the positive control. Without it these would be four
assertions that happen to hold, and there would be no evidence they are
sensitive to anything.

## The honesty boundary

You cannot test *"no function from bank line to ledger field exists."* You can
test that an enumerated family of functions does not exist, and you can make
the structural argument -- `corpus/generator/bank.py` takes a `Payout` carrying
an amount and a timestamp and is never passed a settlement identifier. The
pairing is the defensible position. Claiming the universal negative is not.

## What is allowed to leak, by name

1. **amount** -- the credit is the credit. This MUST leak; it is the join
   evidence and the reason reconciliation is possible at all.
2. **posting date within a few days of settlement** -- money really does land
   near the settlement date.
3. **counterparty text naming Razorpay** -- it really is the remitter.

Everything else on the bank line must be the bank's own.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IST = timezone(timedelta(hours=5, minutes=30))
DATASETS = ROOT / "corpus" / "datasets"
FROZEN = ROOT / "engine" / "data"

#: exactly `settlement_id[-6:]`, the length of the frozen leak. Shorter
#: thresholds false-positive on ordinary English narration tokens.
MIN_SHARED = 6

#: Columns whose sharing with the bank is legitimate (see the module docstring).
PERMITTED_LEDGER_FIELDS = {"credit", "debit", "amount"}

IDENTIFIER_FIELDS = ("settlement_id", "entity_id", "order_id",
                     "order_receipt", "payment_id", "dispute_id")

#: `settlement_utr` is DELIBERATELY not in that list, and the reason is the
#: whole of D4 stated precisely.
#:
#: The PSP genuinely knows the bank's reference -- it initiated the transfer --
#: so `settlement_utr` carrying the bank's real reference is the legitimate
#: attestation channel, and it is the link the entire corpus depends on. The
#: DIRECTION of derivation is what matters: bank -> PSP is a report, PSP ->
#: bank is a fabrication.
#:
#: So the test is not "does the reference appear in both files" -- it must --
#: but "**is the reference reconstructible from ledger fields alone**". On the
#: frozen set it is: `utr == str(settled_at) + settlement_id[-6:]`, so the bank
#: file adds no information a solver did not already hold. That is checked
#: directly by `reference_is_derivable` below.


def corpus_datasets() -> list[Path]:
    """Both families. `datasets_v2` is a superset generation at new seeds, not
    a correction of `datasets`, and every guarantee here binds on both."""
    out: list[Path] = []
    for family in (DATASETS, DATASETS.parent / "datasets_v2"):
        if family.exists():
            out += sorted(p for p in family.iterdir()
                          if (p / "bank_statement.csv").exists())
    return out


def _bank(directory: Path) -> tuple[list[dict], str, str]:
    with (directory / "bank_statement.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    reference = "bank_reference" if rows and "bank_reference" in rows[0] else "utr"
    when = "value_date" if rows and "value_date" in rows[0] else "date"
    return rows, reference, when


def _rows(directory: Path) -> list[dict]:
    return json.loads((directory / "recon_combined.json").read_text())["items"]


# --------------------------------------------------------------------------
# 1. string recoverability
# --------------------------------------------------------------------------


def string_leaks(directory: Path) -> list[str]:
    """Any ledger identifier appearing inside any bank cell."""
    bank, _reference, _when = _bank(directory)
    blob = " ".join(str(value) for row in bank for value in row.values())
    found = []
    for row in _rows(directory):
        for field in IDENTIFIER_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and len(value) >= MIN_SHARED and value in blob:
                found.append(f"{field}={value!r} appears in the bank file")
            # the frozen leak is a SLICE, not the whole id
            if isinstance(value, str) and len(value) > MIN_SHARED \
                    and value[-MIN_SHARED:] in blob:
                found.append(f"{field}[-{MIN_SHARED}:]={value[-MIN_SHARED:]!r} "
                             "appears in the bank file")
    return sorted(set(found))[:8]


@pytest.mark.parametrize("dataset", corpus_datasets(), ids=lambda p: p.name)
def test_no_ledger_identifier_appears_in_the_bank_file(dataset):
    assert string_leaks(dataset) == []


def test_the_string_check_FAILS_on_the_frozen_bank_file():
    """The positive control. If this ever passes, the check has gone blind."""
    leaks = string_leaks(FROZEN)
    assert leaks, ("the frozen bank file is known to embed settlement_utr and "
                   "settlement_id[-6:]; a check that cannot see that proves "
                   "nothing about the corpus")


# --------------------------------------------------------------------------
# 1b. is the attestation reference RECONSTRUCTIBLE from ledger fields?
# --------------------------------------------------------------------------


def reference_is_derivable(directory: Path) -> list[str]:
    """D4, stated exactly: can the reference be computed from ledger state?

    If it can, the bank file is a re-encoding of the attestation and
    "matched on UTR" measures the generator rather than a solver.
    """
    found = []
    for row in _rows(directory):
        reference = row.get("settlement_utr")
        settlement_id = row.get("settlement_id")
        stamp = row.get("settled_at")
        if not (reference and settlement_id and stamp):
            continue
        if reference == f"{stamp}{settlement_id[-6:]}":
            found.append(f"{reference!r} == str(settled_at) + "
                         "settlement_id[-6:]")
        elif reference.startswith(str(stamp)):
            found.append(f"{reference!r} starts with settled_at {stamp}")
        elif settlement_id[-6:] in reference:
            found.append(f"{reference!r} contains settlement_id[-6:]")
    return sorted(set(found))[:8]


@pytest.mark.parametrize("dataset", corpus_datasets(), ids=lambda p: p.name)
def test_the_attestation_reference_is_not_reconstructible_from_the_ledger(dataset):
    assert reference_is_derivable(dataset) == []


def test_the_derivability_check_FAILS_on_the_frozen_dataset():
    """Measured: 11 of 11 frozen batches. The positive control for D4 itself."""
    assert reference_is_derivable(FROZEN), (
        "the frozen settlement_utr is str(settled_at) + settlement_id[-6:] on "
        "every batch; a check that cannot see that is not a check")


# --------------------------------------------------------------------------
# 2. arithmetic recoverability
# --------------------------------------------------------------------------


def arithmetic_leaks(directory: Path) -> list[str]:
    """A digit run in a bank cell equal to a ledger timestamp."""
    bank, _reference, _when = _bank(directory)
    stamps = {str(row["settled_at"]) for row in _rows(directory)
              if row.get("settled_at")}
    stamps |= {str(int(value) // 86400) for value in stamps}
    found = []
    for row in bank:
        for value in row.values():
            text = str(value)
            run = ""
            for character in text + " ":
                if character.isdigit():
                    run += character
                else:
                    if len(run) >= 8 and run in stamps:
                        found.append(f"{run!r} is a ledger timestamp, in {text!r}")
                    run = ""
    return sorted(set(found))[:8]


@pytest.mark.parametrize("dataset", corpus_datasets(), ids=lambda p: p.name)
def test_no_ledger_timestamp_is_embedded_in_the_bank_file(dataset):
    assert arithmetic_leaks(dataset) == []


def test_the_arithmetic_check_FAILS_on_the_frozen_bank_file():
    """`utr = f"{t}{settlement_id[-6:]}"` -- `t` IS `settled_at`."""
    assert arithmetic_leaks(FROZEN), (
        "the frozen UTR is str(settled_at) concatenated with six id "
        "characters; the check must see it")


# --------------------------------------------------------------------------
# 3. the bank has a clock of its own
# --------------------------------------------------------------------------


def _settlement_dates(directory: Path) -> list:
    return sorted({datetime.fromtimestamp(row["settled_at"], IST).date()
                   for row in _rows(directory) if row.get("settled_at")})


def posting_lags(directory: Path) -> dict[int, int]:
    bank, _reference, when = _bank(directory)
    settled = _settlement_dates(directory)
    lags: dict[int, int] = {}
    for index, row in enumerate(bank):
        if index >= len(settled):
            break
        try:
            posted = date.fromisoformat(row[when])
        except ValueError:                       # pragma: no cover - defensive
            continue
        lag = (posted - settled[index]).days
        lags[lag] = lags.get(lag, 0) + 1
    return lags


@pytest.mark.parametrize("dataset", corpus_datasets(), ids=lambda p: p.name)
def test_the_posting_lag_is_not_constant(dataset):
    """A constant lag means the bank has no clock -- the value date IS
    `settled_at`, and a withheld column is handed straight back.

    NOT MEASURABLE at the PSP-absence axis points: the recon feed carries no
    `settled_at`, so there is no settlement date to measure a lag against. The
    distribution is empty for the same reason a coin never flipped has no
    distribution, and asserting on it would be this suite gating an unmeasured
    quantity -- the error class the whole corpus exists to find. Skipped with
    the reason rather than passed silently.
    """
    if not _settlement_dates(dataset):
        pytest.skip("no settled_at in this feed: posting lag is not measurable, "
                    "not constant (PSP-absence axis point)")
    assert len(posting_lags(dataset)) > 1


def test_the_lag_check_FAILS_on_the_frozen_bank_file():
    """Measured: every frozen bank line posts on its settlement date."""
    assert len(posting_lags(FROZEN)) == 1, (
        "the frozen posting lag is 0 days on all 12 lines")


# --------------------------------------------------------------------------
# 4. the bank file is not a list of our settlements
# --------------------------------------------------------------------------


@pytest.mark.parametrize("dataset", corpus_datasets(), ids=lambda p: p.name)
def test_the_bank_file_is_not_a_bijection_with_the_batch_list(dataset):
    """The frozen file has 12 lines for 12 batches, one each, in order, with
    no foreign credits and no debits -- so the resolver never has to answer
    *"is this credit even ours?"*, and `n_bank_lines == n_settlements` is a
    free prior. Foreign lines remove both."""
    truth = json.loads((dataset / "ground_truth.json").read_text())
    kinds = {line["kind"] for line in truth["bank_lines"]}
    assert kinds - {"settlement"}, "no non-settlement lines in the bank file"
    assert len(truth["bank_lines"]) > len(truth["batches"])


def test_the_bijection_check_FAILS_on_the_frozen_bank_file():
    frozen_bank, _reference, _when = _bank(FROZEN)
    truth = json.loads((ROOT / "engine" / "ground_truth" /
                        "ground_truth.json").read_text())
    assert len(frozen_bank) == len(truth["batches"]) == 12, (
        "the frozen bank file is a 12-line bijection with 12 batches")


# --------------------------------------------------------------------------
# 5. the bank's counter is not ours
# --------------------------------------------------------------------------


@pytest.mark.parametrize("dataset", corpus_datasets(), ids=lambda p: p.name)
def test_the_bank_reference_sequence_has_gaps(dataset):
    """A dense gapless counter is a counter minted for this file. A real
    branch clears other customers' NEFT between ours."""
    bank, reference, _when = _bank(dataset)
    digits = sorted(int("".join(c for c in row[reference] if c.isdigit()))
                    for row in bank if row[reference])
    assert len(digits) >= 3
    steps = {b - a for a, b in zip(digits, digits[1:])}
    assert steps != {1}, "the reference sequence is dense; it has no gaps"


@pytest.mark.parametrize("dataset", corpus_datasets(), ids=lambda p: p.name)
def test_some_bank_lines_do_not_share_a_date_with_their_settlement(dataset):
    """The join a resolver gets for free when lag is zero."""
    truth = json.loads((dataset / "ground_truth.json").read_text())
    lags = [line["posting_lag_days"] for line in truth["bank_lines"]
            if line["posting_lag_days"] is not None]
    assert lags and any(lag > 0 for lag in lags)
