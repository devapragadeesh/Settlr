"""The held-out set must not have cost the frozen set a single byte.

Phase 4 generates a second dataset with the SAME generator. The whole value of
that depends on two properties a reader should not have to take on trust:

  1. `engine/` is byte-identical afterwards -- the generator was driven as a
     library, never edited;
  2. the held-out set shares no identifier, timestamp or invoice number with
     the primary set, so neither can contaminate the other.

Both are asserted here rather than asserted in a markdown file.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOLDOUT = ROOT / "holdout"

#: every path the phase brief freezes.
FROZEN = [
    "engine/generator.py",
    "engine/simulator.py",
    "engine/DATASET_HASHES.txt",
    "engine/data/recon_combined.json",
    "engine/data/disputes.json",
    "engine/data/bank_statement.csv",
    "engine/data/erp_orders.csv",
    "engine/data/gstr2b.csv",
    "engine/ground_truth/ground_truth.json",
]

pytestmark = pytest.mark.skipif(
    not (HOLDOUT / "data" / "recon_combined.json").exists(),
    reason="held-out set not generated")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text())


def column(path: Path, key: str) -> set[str]:
    with path.open(newline="") as handle:
        return {line[key] for line in csv.DictReader(handle) if line[key]}


# --- 1. the freeze ----------------------------------------------------------


def test_the_committed_hashes_still_describe_the_frozen_files():
    """`engine/DATASET_HASHES.txt` is the primary set's own attestation."""
    for line in (ROOT / "engine" / "DATASET_HASHES.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        expected, _, relative = line.partition(" ")
        assert digest(ROOT / relative.strip()) == expected, relative


def test_generating_the_holdout_set_leaves_engine_byte_identical(tmp_path):
    """The strong form: run the held-out generator and hash `engine/` around it.

    This is what makes "the generator is unmodified" a checked property rather
    than a claim in a README. If `holdout/generate_holdout.py` ever writes to
    `engine/` -- or edits the generator to change the period instead of
    rebinding it on the imported module -- this fails.
    """
    before = {name: digest(ROOT / name) for name in FROZEN}
    completed = subprocess.run(
        [sys.executable, str(HOLDOUT / "generate_holdout.py")],
        capture_output=True, text=True, cwd=ROOT)
    assert completed.returncode == 0, completed.stderr
    after = {name: digest(ROOT / name) for name in FROZEN}
    changed = sorted(name for name in FROZEN if before[name] != after[name])
    assert not changed, f"generating the held-out set modified: {changed}"


def test_the_holdout_generator_never_names_a_write_into_engine():
    text = (HOLDOUT / "generate_holdout.py").read_text()
    for forbidden in ("write_text", "write_bytes"):
        for line in text.splitlines():
            if forbidden in line:
                assert "engine" not in line, line


def test_the_holdout_set_carries_its_own_hash_file():
    lines = [l for l in (HOLDOUT / "DATASET_HASHES.txt").read_text().splitlines()
             if l and not l.startswith("#")]
    assert lines
    for line in lines:
        expected, _, relative = line.partition(" ")
        assert relative.strip().startswith("holdout/"), relative
        assert digest(ROOT / relative.strip()) == expected, relative


# --- 2. disjointness --------------------------------------------------------


def test_no_entity_id_order_id_or_timestamp_is_shared_with_the_primary_set():
    primary = load_json(ROOT / "engine/data/recon_combined.json")["items"]
    holdout = load_json(HOLDOUT / "data/recon_combined.json")["items"]
    for key in ("entity_id", "order_id", "created_at"):
        shared = ({row[key] for row in primary if row[key]}
                  & {row[key] for row in holdout if row[key]})
        assert not shared, f"{key} shared between the two sets: {sorted(shared)[:5]}"


def test_no_utr_settlement_id_or_invoice_number_is_shared():
    assert not (column(ROOT / "engine/data/bank_statement.csv", "utr")
                & column(HOLDOUT / "data/bank_statement.csv", "utr"))
    for name in ("erp_orders.csv", "gstr2b.csv"):
        assert not (column(ROOT / "engine/data" / name, "invoice_no")
                    & column(HOLDOUT / "data" / name, "invoice_no")), name
    primary = load_json(ROOT / "engine/ground_truth/ground_truth.json")
    holdout = load_json(HOLDOUT / "ground_truth/ground_truth.json")
    assert not ({b["settlement_id"] for b in primary["batches"]}
                & {b["settlement_id"] for b in holdout["batches"]})


def test_the_periods_do_not_overlap():
    primary = load_json(ROOT / "engine/data/recon_combined.json")["items"]
    holdout = load_json(HOLDOUT / "data/recon_combined.json")["items"]
    assert min(row["created_at"] for row in holdout) > \
        max(row["created_at"] for row in primary)


def test_the_seed_is_the_one_that_was_committed():
    committed = next(
        line.split("=")[1].strip()
        for line in (HOLDOUT / "SEED.txt").read_text().splitlines()
        if line.startswith("HELDOUT_SEED"))
    assert load_json(HOLDOUT / "ground_truth/ground_truth.json")["seed"] \
        == int(committed)


# --- 3. the unseen class ----------------------------------------------------


def test_the_primary_set_contains_no_reversal():
    """`h01` is only meaningful if the engine has never seen one. The primary
    bank statement must be all credits."""
    with (ROOT / "engine/data/bank_statement.csv").open(newline="") as handle:
        amounts = [line["amount"] for line in csv.DictReader(handle)]
    assert not [a for a in amounts if a.startswith("-")], \
        "the primary set already contains a debit line; h01 is not unseen"
    primary = load_json(ROOT / "engine/ground_truth/ground_truth.json")
    assert "planted_reversals" not in primary


def test_the_holdout_set_contains_the_planted_reversals():
    truth = load_json(HOLDOUT / "ground_truth/ground_truth.json")
    records = truth["planted_reversals"]
    assert 2 <= len(records) <= 3
    with (HOLDOUT / "data/bank_statement.csv").open(newline="") as handle:
        bank = list(csv.DictReader(handle))
    debits = [line for line in bank if line["amount"].startswith("-")]
    assert len(debits) == len(records)

    by_utr = {line["utr"]: line for line in bank}
    for record in records:
        # the debit reverses the original credit exactly, and references UTR-A
        debit = next(d for d in debits if d["utr"] == record["original_utr"])
        assert debit["amount"] == f"-{record['payout_paise'] // 100}." \
                                  f"{record['payout_paise'] % 100:02d}"
        assert record["original_utr"] in debit["narration"]
        assert "RET" in debit["narration"]
        # the re-settlement credit duplicates the original's composition
        credit_b = by_utr[record["resettlement_utr"]]
        assert credit_b["amount"] == f"{record['payout_paise'] // 100}." \
                                     f"{record['payout_paise'] % 100:02d}"
        assert debit["date"] > record["original_credit_date"]
        assert credit_b["date"] >= debit["date"]


def test_the_reversal_linkage_is_recoverable_in_both_directions():
    truth = load_json(HOLDOUT / "ground_truth/ground_truth.json")
    by_id = {b["settlement_id"]: b for b in truth["batches"]}
    for record in truth["planted_reversals"]:
        original = by_id[record["original_settlement_id"]]
        new = by_id[record["resettlement_settlement_id"]]
        assert original["reversed_by"] == new["settlement_id"]
        assert new["resettlement_of"] == original["settlement_id"]
        # the rows moved: the original batch is now empty, the new one holds them
        assert original["credit_ids"] == [] and original["debit_ids"] == []
        assert sorted(new["credit_ids"] + new["debit_ids"]) == record["row_ids"]
        for row_id in record["row_ids"]:
            assert truth["settled_in"][row_id] == new["settlement_id"]


def test_the_moved_rows_attest_the_new_utr_in_the_shipped_data():
    truth = load_json(HOLDOUT / "ground_truth/ground_truth.json")
    rows = {row["entity_id"]: row
            for row in load_json(HOLDOUT / "data/recon_combined.json")["items"]}
    for record in truth["planted_reversals"]:
        for row_id in record["row_ids"]:
            row = rows[row_id]
            assert row["settlement_id"] == record["resettlement_settlement_id"]
            # adjustment rows carry a null UTR even with a real sid (c12);
            # the extension must not repair that planted quirk
            if row["type"] == "adjustment":
                assert row["settlement_utr"] is None
            else:
                assert row["settlement_utr"] == record["resettlement_utr"]


#: tokens that would tell a solver where the reversals are. Deliberately the
#: LABEL vocabulary, not the English word "reversal": the frozen generator has
#: always emitted an adjustment described "Fee reversal - overcharged MDR"
#: (generator.py L496), which occurs three times in the PRIMARY set and is
#: therefore pre-existing ledger vocabulary rather than anything Phase 4
#: introduced. A first draft of this test banned the bare word and failed on
#: it. Narrowing the token is correct; the alternative -- carving out one
#: phrase -- would have made the test unable to catch a real leak that happened
#: to contain it.
REVERSAL_LABEL_TOKENS = ("h01", "reversed_by", "resettlement_of",
                         "resettlement_settlement_id", "planted_reversals",
                         "ground_truth", "original_settlement_id")


def test_the_reversal_wording_that_is_NOT_a_leak_is_genuinely_pre_existing():
    """Justifies narrowing the token list above, rather than trusting it."""
    assert "Fee reversal - overcharged MDR" in (ROOT / "engine/generator.py").read_text()
    primary = (ROOT / "engine/data/recon_combined.json").read_text()
    assert "Fee reversal - overcharged MDR" in primary


def test_the_holdout_data_does_not_leak_the_reversal_labels():
    """Same rule as the primary set: the answer key is isolated."""
    for path in sorted((HOLDOUT / "data").iterdir()):
        text = path.read_text().lower()
        for token in REVERSAL_LABEL_TOKENS:
            assert token not in text, f"{path.name} leaks {token!r}"


def test_the_holdout_data_carries_no_more_reversal_wording_than_the_primary():
    """The distributional form of the same check: if planting h01 had made the
    word `reversal` commoner in the held-out data, that alone would be a
    signal a matcher could key on, even with no label present."""
    import re
    def rate(path):
        rows = load_json(path)["items"]
        hits = sum(1 for row in rows
                   if re.search("reversal", str(row.get("description") or ""), re.I))
        return hits / len(rows)
    primary = rate(ROOT / "engine/data/recon_combined.json")
    holdout = rate(HOLDOUT / "data/recon_combined.json")
    assert holdout <= primary * 2, (primary, holdout)
