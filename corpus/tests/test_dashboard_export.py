"""dashboard/data.json must match its source artefacts EXACTLY.

The export layer's whole justification (corpus/export_dashboard.py's own
docstring, DASHBOARD_DATA.md) is that a figure the dashboard shows has one
owner. This test is the mechanism that keeps that true: it re-reads the
source artefacts independently and asserts the export did not drift from
them, silently recompute anything, or invent a field with no source.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus import claims_ledger, coverage as coverage_mod   # noqa: E402

ORACLE = ROOT / "corpus" / "oracle_results.json"
BASELINE = ROOT / "corpus" / "baseline_results.json"
EXPORT = ROOT / "dashboard" / "data.json"

pytestmark = pytest.mark.skipif(
    not ORACLE.exists(), reason="corpus/oracle_results.json not generated")


@pytest.fixture(scope="module")
def export(tmp_path_factory) -> dict:
    """Export to a TEMP path, never over the tracked `dashboard/data.json`.

    This fixture used to run the exporter with no `--out`, so it overwrote the
    committed artifact every time the suite ran. Two consequences, both real:
    `git status` came back dirty after any test run, which makes a scope check
    before a commit useless; and because `commit_ordering.count` is a live
    `git log` count, the tracked file went stale on every commit and was
    silently rewritten by the next test run. A test that mutates the tree it
    is verifying cannot tell you the tree was already correct.

    `export_dashboard.py` already accepted `--out`; the fixture simply was not
    using it. Regenerating the real artifact stays a deliberate act -- run
    `python3 corpus/export_dashboard.py` yourself, or `run_all.py` step 7.
    """
    out = tmp_path_factory.mktemp("dashboard") / "data.json"
    subprocess.run([sys.executable, "corpus/export_dashboard.py",
                    "--skip-hashes", "--out", str(out)], cwd=ROOT, check=True,
                   capture_output=True)
    return json.loads(out.read_text())


def test_claims_match_the_claims_ledger_exactly(export):
    """The export's `claims` must be `corpus.claims_ledger.rows()` verbatim,
    not a re-derivation -- the whole point of reusing the function directly.
    """
    assert export["claims"] == claims_ledger.rows()


def test_coverage_matches_corpus_coverage_split_exactly(export):
    oracle = json.loads(ORACLE.read_text())
    for scope in coverage_mod.SCOPES:
        expected = coverage_mod.split(oracle, scope)
        assert export["coverage"][scope] == expected, (
            f"scope {scope!r} drifted from corpus.coverage.split()")


def test_three_systems_per_dataset_count_matches_oracle(export):
    oracle = json.loads(ORACLE.read_text())
    assert len(export["three_systems"]["per_dataset"]) == len(oracle)


def test_three_systems_frozen_column_matches_baseline_results_when_present(export):
    if not BASELINE.exists():
        pytest.skip("corpus/baseline_results.json not generated")
    baseline = json.loads(BASELINE.read_text())
    by_key = {f"{r.get('family', 'datasets')}/{r['dataset']}": r for r in baseline}
    for row in export["three_systems"]["per_dataset"]:
        key = row["dataset"]
        source = by_key.get(key)
        exported_frozen = row["frozen"]
        if source is None or not source.get("ran", True):
            assert not exported_frozen.get("ran")
            continue
        # frozen_row() derives `attempted` from the source's own outcomes --
        # re-derive independently here rather than importing frozen_row, so
        # this test does not just call the function under test on itself.
        determinate = source["outcomes"].get("Determinate", 0)
        expected_attempted = determinate
        assert exported_frozen["attempted"] == expected_attempted, (
            f"{key}: export's frozen.attempted drifted from "
            "baseline_results.json's own Determinate count")


def test_d15_matches_the_committed_scorecard_constant(export):
    from corpus.scorecard import D15
    exported = {k: v for k, v in export["d15"].items() if k != "source"}
    assert exported == D15


def test_export_invents_no_field_the_repo_does_not_own(export):
    """The self-correction record must be a citation, not a number -- this
    is the one field this export is explicitly forbidden from computing.
    Watched to fail: temporarily hand this a fabricated integer count and
    confirm this assertion catches it before trusting it.
    """
    record = export["self_correction_record"]
    assert record["available_as_number"] is False
    assert "count" not in record
