"""Sweep every case in `cases.py` through `resolver.loaders.load` +
`resolver.resolve.resolve` -- the resolver's real, public entry point, called
read-only, never monkeypatched -- and classify the result with
`bucket.classify_resolver`.

Only bucket 3 (a silent, plausible-looking wrong answer) fails a test here.
Bucket 2 (an uncaught low-level exception) is allowed, but its exact type is
asserted so a change in *which* exception fires is visible -- the point
`DECISIONS.md` 52 makes explicitly: this suite is not a request to harden
`resolver/` against these inputs.
"""

from __future__ import annotations

import pytest

from .bucket import BUCKET_SILENT_WRONG_ANSWER, classify_resolver
from .cases import ALL_CASES
from .conftest import clone_dataset

RESOLVER_CASES = [case for case in ALL_CASES if "resolver" in case.targets]


@pytest.mark.parametrize("case", RESOLVER_CASES, ids=lambda c: f"{c.surface}.{c.name}")
def test_resolver_never_returns_a_silent_wrong_answer(
        case, resolver_baseline, tmp_path):
    dataset_dir = clone_dataset(resolver_baseline, tmp_path)
    meta = case.mutate(dataset_dir)
    outcome = classify_resolver(dataset_dir, meta.get("target_bank_index"))

    assert outcome.bucket != BUCKET_SILENT_WRONG_ANSWER, (
        f"resolver bucket-3 finding on {case.surface}.{case.name}: "
        f"{outcome.detail} -- see ADVERSARIAL_FINDINGS.md, do not patch "
        "resolver/ to make this test pass")


# ---------------------------------------------------------------------------
# regression protection for bucket-2 cases: pin the exact exception type so a
# silent change from "raises KeyError" to "returns a result" is visible.
# ---------------------------------------------------------------------------

EXPECTED_BUCKET_2_EXCEPTIONS = {
    "recon.truncated_json": "JSONDecodeError",
    "recon.missing_items_key": "KeyError",
    # Was "KeyError": the loader subscripted line["value_date"] directly.
    # Since 2026-09-03 `_bank_column` checks the header first and raises a
    # ValueError naming BOTH accepted spellings and the header it actually
    # found -- strictly more informative than a bare KeyError, and the same
    # bucket (2) either way. matching/ is frozen and still raises KeyError.
    "bank.missing_header_column": "ValueError",
    "bank.non_numeric_amount": "ValueError",
    "bank.blank_value_date": "ValueError",
    "settlement_report.missing_reported_amount_column": "KeyError",
    "settlement_report.non_numeric_amount": "ValueError",
    # Was None: resolver's paise used to TRUNCATE silently while
    # matching.money.paise rejected the same cell. Fixed 2026-09-03 --
    # both parsers now enforce the same grammar, so both raise here and
    # this expectation matches test_matching_survives.py's exactly.
    "bank.over_precision_amount": "ValueError",
    # All three were bucket 1 until 2026-09-03, each for a SILENT reason:
    # a duplicate settlement_id overwrote the earlier attestation, an
    # unrecognised disputes.json shape became an empty dispute set, and an
    # item with no id collapsed to the key "". The loader now refuses all
    # three, so they raise here. tests/adversarial/bucket.py is deliberately
    # NOT extended to count these as typed declines: raising the bucket-1
    # count by editing the bucket definition in the same pass that is scored
    # by it would be scoring our own homework.
    "settlement_report.duplicate_settlement_id": "ValueError",
    "disputes.malformed_shape": "ValueError",
    "disputes.missing_id": "ValueError",
}


@pytest.mark.parametrize(
    "case", [c for c in RESOLVER_CASES
             if f"{c.surface}.{c.name}" in EXPECTED_BUCKET_2_EXCEPTIONS],
    ids=lambda c: f"{c.surface}.{c.name}")
def test_resolver_exception_type_is_pinned(case, resolver_baseline, tmp_path):
    dataset_dir = clone_dataset(resolver_baseline, tmp_path)
    meta = case.mutate(dataset_dir)
    outcome = classify_resolver(dataset_dir, meta.get("target_bank_index"))
    expected = EXPECTED_BUCKET_2_EXCEPTIONS[f"{case.surface}.{case.name}"]
    if expected is None:
        assert outcome.exception_type == "", (
            f"{case.surface}.{case.name} was expected to load without "
            f"raising (the known silent-truncate behaviour); it raised "
            f"{outcome.exception_type!r} instead -- if resolver.loaders.paise "
            "now validates precision, update this expectation and "
            "ADVERSARIAL_FINDINGS.md together")
    else:
        assert outcome.exception_type == expected, (
            f"{case.surface}.{case.name} used to raise {expected}, now "
            f"raises {outcome.exception_type!r} (or nothing) -- a change in "
            "failure mode on malformed input, worth a deliberate look")
