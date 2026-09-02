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
    "bank.missing_header_column": "KeyError",
    "bank.non_numeric_amount": "ValueError",
    "bank.blank_value_date": "ValueError",
    "settlement_report.missing_reported_amount_column": "KeyError",
    "settlement_report.non_numeric_amount": "ValueError",
    "bank.over_precision_amount": None,  # resolver's paise TRUNCATES silently
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
