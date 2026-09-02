"""Sweep every relevant case in `cases.py` through `matching.loaders.load` +
`matching.cascade.run` (via `matching.run`, the frozen cascade's public entry
point) -- read-only, never monkeypatched -- and classify with
`bucket.classify_matching`.

`settlement_report.csv` cases are excluded: `matching/loaders.py` never
reads that file (see `conftest.py`), so they have nothing to corrupt from
this package's point of view.

As in `test_resolver_survives.py`, only bucket 3 fails a test.
"""

from __future__ import annotations

import pytest

from .bucket import BUCKET_SILENT_WRONG_ANSWER, classify_matching
from .cases import ALL_CASES
from .conftest import clone_dataset

MATCHING_CASES = [case for case in ALL_CASES if "matching" in case.targets]


@pytest.mark.parametrize("case", MATCHING_CASES, ids=lambda c: f"{c.surface}.{c.name}")
def test_matching_never_returns_a_silent_wrong_answer(
        case, matching_baseline, tmp_path):
    dataset_dir = clone_dataset(matching_baseline, tmp_path)
    meta = case.mutate(dataset_dir)
    outcome = classify_matching(dataset_dir, meta.get("target_bank_index"))

    assert outcome.bucket != BUCKET_SILENT_WRONG_ANSWER, (
        f"matching bucket-3 finding on {case.surface}.{case.name}: "
        f"{outcome.detail} -- see ADVERSARIAL_FINDINGS.md, do not patch "
        "matching/ to make this test pass")


EXPECTED_BUCKET_2_EXCEPTIONS = {
    "recon.truncated_json": "JSONDecodeError",
    "recon.missing_items_key": "KeyError",
    "bank.missing_header_column": "KeyError",
    "bank.non_numeric_amount": "ValueError",
    "bank.over_precision_amount": "ValueError",  # matching.money.paise REJECTS
    "disputes.malformed_shape": "KeyError",       # no dual-handling, unlike resolver
}


@pytest.mark.parametrize(
    "case", [c for c in MATCHING_CASES
             if f"{c.surface}.{c.name}" in EXPECTED_BUCKET_2_EXCEPTIONS],
    ids=lambda c: f"{c.surface}.{c.name}")
def test_matching_exception_type_is_pinned(case, matching_baseline, tmp_path):
    dataset_dir = clone_dataset(matching_baseline, tmp_path)
    meta = case.mutate(dataset_dir)
    outcome = classify_matching(dataset_dir, meta.get("target_bank_index"))
    expected = EXPECTED_BUCKET_2_EXCEPTIONS[f"{case.surface}.{case.name}"]
    assert outcome.exception_type == expected, (
        f"{case.surface}.{case.name} used to raise {expected}, now raises "
        f"{outcome.exception_type!r} (or nothing) -- a change in failure "
        "mode on malformed input, worth a deliberate look")
