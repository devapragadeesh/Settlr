"""The two additions that answer CHECKPOINT 0.1, tested as claims.

0.1 said the corpus is solvable by a fifteen-line `GROUP BY` because
`settlement_id` is populated everywhere and never false. Two datasets families
answer it and each makes a specific claim:

* the PSP-absence points carry **no settlement fields at all**, so the trivial
  predicate is not expressible;
* `datasets_v2` plants one `settlement_id` that names rows which are **not**
  the batch's composition, **and the arithmetic still closes**, so the trivial
  predicate is expressible and wrong.

Both claims are checkable without reading any resolver. They are checked here.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "corpus"
ABSENCE = ["A20_Bnone_Cmax", "A40_Bnone_Cmax"]
SETTLEMENT_FIELDS = ("settlement_id", "settled", "settled_at", "settlement_utr")


def _rows(dataset: Path) -> list[dict]:
    return json.loads((dataset / "recon_combined.json").read_text())["items"]


def _truth(dataset: Path) -> dict:
    return json.loads((dataset / "ground_truth.json").read_text())


def v2_datasets() -> list[Path]:
    family = CORPUS / "datasets_v2"
    if not family.exists():
        return []
    return sorted(p for p in family.iterdir()
                  if (p / "ground_truth.json").exists())


# --------------------------------------------------------------------------
# 1. absence really is absence
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ABSENCE)
def test_no_settlement_field_survives_at_the_absence_points(name):
    """All four settlement columns are ABSENT, not null.

    Dropping only `settlement_id` would leave `settled_at` as a perfect group
    key -- the same triviality one column over, which is the error 0.1
    records. The four are one assertion written four ways, so they go together.
    """
    for row in _rows(CORPUS / "datasets" / name):
        for field in SETTLEMENT_FIELDS:
            assert field not in row, f"{field} survives on {row['entity_id']}"


@pytest.mark.parametrize("name", ABSENCE)
def test_no_settlement_report_at_the_absence_points(name):
    """The PSP's attestation artefact does not exist. An empty file with a
    header would still assert 'the PSP made no claims', which is a claim."""
    assert not (CORPUS / "datasets" / name / "settlement_report.csv").exists()


@pytest.mark.parametrize("name", ABSENCE)
def test_the_absence_points_still_have_reconstructible_instances(name):
    """Otherwise the cell would be unscoreable: gate G8 needs a subpopulation
    the corpus can PROVE has exactly one answer, or abstention is free again
    (contract 6.4)."""
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from corpus.oracle import reconstructible_instances

    truth = _truth(CORPUS / "datasets" / name)
    assert truth["determined_instances"] == [], (
        "determinedness requires an attestation and there is none here")
    assert len(reconstructible_instances(truth)) >= 1


@pytest.mark.parametrize("name", ABSENCE)
def test_the_bank_file_is_unchanged_in_shape_by_absence(name):
    """Only the PSP artefacts go away. The bank still posts money, which is
    what makes the cell reconstruction rather than nothing."""
    with (CORPUS / "datasets" / name / "bank_statement.csv").open() as handle:
        bank = list(csv.DictReader(handle))
    assert len(bank) >= 12
    assert any(float(line["amount"]) > 0 for line in bank)


# --------------------------------------------------------------------------
# 2. the false attestation closes, and is wrong
# --------------------------------------------------------------------------


@pytest.mark.parametrize("dataset", v2_datasets(), ids=lambda p: p.name)
def test_the_false_attestation_closes_arithmetically(dataset):
    """The whole point: a sum check cannot see it.

    If the swapped rows did not net identically, the naive baseline would
    catch the plant with the one check it already performs, and the class
    would be testing nothing.
    """
    truth = _truth(dataset)
    rows = {row["entity_id"]: row for row in _rows(dataset)}
    planted = truth["planted_classes"]["d11_false_settlement_id"]
    if not planted["planted"]:
        pytest.skip(planted["reason"])
    for item in planted["detail"]:
        net = lambda ids: sum(rows[r]["credit"] - rows[r]["debit"] for r in ids)
        assert net(item["attested_composition"]) == item["true_payout_paise"]
        assert net(item["true_composition"]) == item["true_payout_paise"]
        assert net(item["rows_removed"]) == net(item["rows_added"])


@pytest.mark.parametrize("dataset", v2_datasets(), ids=lambda p: p.name)
def test_the_false_attestation_is_actually_false(dataset):
    """It names rows that are not the composition -- checked against the KEY,
    and against the emitted file, because a plant recorded in ground truth but
    not written to the data would be a benchmark lying to itself."""
    truth = _truth(dataset)
    planted = truth["planted_classes"]["d11_false_settlement_id"]
    if not planted["planted"]:
        pytest.skip(planted["reason"])
    rows = _rows(dataset)
    for item in planted["detail"]:
        assert set(item["attested_composition"]) != set(item["true_composition"])
        emitted = {row["entity_id"] for row in rows
                   if row.get("settlement_id") == item["settlement_id"]}
        assert emitted == set(item["attested_composition"]), (
            "the emitted file does not carry the plant the key describes")


@pytest.mark.parametrize("dataset", v2_datasets(), ids=lambda p: p.name)
def test_the_false_attestation_is_discoverable_by_reconciliation(dataset):
    """Every added row was created AFTER the bank's value date for the line.

    A row that did not exist when the money left cannot have been in the money
    that left. That is a contradiction between the PSP's `created_at` and the
    BANK's `value_date` -- two parties -- so the plant is findable by the
    independent check `Verified` is supposed to rest on, and not by grepping.
    """
    from datetime import date, datetime, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    truth = _truth(dataset)
    planted = truth["planted_classes"]["d11_false_settlement_id"]
    if not planted["planted"]:
        pytest.skip(planted["reason"])
    rows = {row["entity_id"]: row for row in _rows(dataset)}
    for item in planted["detail"]:
        value_date = date.fromisoformat(item["bank_value_date"])
        created = [datetime.fromtimestamp(rows[r]["created_at"], ist).date()
                   for r in item["rows_added"]]
        assert all(when > value_date for when in created), (
            f"{item['settlement_id']}: an added row predates the credit, so "
            "the plant is not discoverable by the temporal check")


@pytest.mark.parametrize("dataset", v2_datasets(), ids=lambda p: p.name)
def test_no_row_was_minted_for_the_plant(dataset):
    """D5. The swap uses rows that already exist and that no batch claims."""
    truth = _truth(dataset)
    planted = truth["planted_classes"]["d11_false_settlement_id"]
    if not planted["planted"]:
        pytest.skip(planted["reason"])
    claimed = {row_id for batch in truth["batches"]
               for row_id in batch["composition"]}
    rows = {row["entity_id"] for row in _rows(dataset)}
    for item in planted["detail"]:
        for row_id in item["rows_added"]:
            assert row_id in rows
            assert row_id not in claimed, (
                "a donated row is another batch's composition; the plant would "
                "damage a second bank line as well as this one")


# --------------------------------------------------------------------------
# 3. the triviality check itself
# --------------------------------------------------------------------------


def test_the_triviality_check_reports_the_original_fourteen_as_trivial():
    """The check must be able to deliver the bad news. If it could not report
    TRIVIAL on the datasets that ARE trivial, it would be decoration."""
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from corpus.triviality_check import run

    results = run([CORPUS / "datasets" / "A20_B100_Cmax"])
    assert results[0]["verdict"] == "TRIVIAL"


def test_the_triviality_check_reports_absence_as_not_expressible():
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from corpus.triviality_check import run

    results = run([CORPUS / "datasets" / "A20_Bnone_Cmax"])
    assert results[0]["verdict"] == "N/A"


@pytest.mark.parametrize("dataset", v2_datasets(), ids=lambda p: p.name)
def test_the_trivial_predicate_is_wrong_where_the_plant_landed(dataset):
    """The point of the whole exercise: on a dataset carrying a false
    settlement_id, trusting the PSP produces a WRONG composition."""
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from corpus.triviality_check import run

    truth = _truth(dataset)
    if not truth["planted_classes"]["d11_false_settlement_id"]["planted"]:
        pytest.skip("no plant at this axis point")
    result = run([dataset])[0]
    assert result["compositions_correct"] < result["compositions_attempted"], (
        "the naive baseline got every composition right on a dataset that "
        "contains a false settlement_id -- the plant is not doing its job")
