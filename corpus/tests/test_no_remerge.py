"""`ProvenUnmatched` + `OpenBreak` must never be summed. `DECISIONS.md` §40.

One outcome asserts something and is gated at zero by G9; the other asserts
nothing and is never gated. A total over both is exactly the conflation
contract §4.7 exists to undo -- it is how a population that was 45.7% accurate
got reported for the life of the project as though it were one claim.

The legacy combined field `OutcomeAccounting.correctly_unmatched` is retained
so the old shape stays readable, which means the re-merge is one attribute
access away. These tests make that access fail in CI rather than in a review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Modules that RENDER numbers for a reader. The prohibition is on reporting a
#: combined total, not on the accounting type continuing to expose one.
REPORTING = [
    ROOT / "corpus" / "score_resolver.py",
    ROOT / "corpus" / "three_systems.py",
    ROOT / "corpus" / "baseline_old_engine.py",
    ROOT / "resolver" / "run.py",
    ROOT / "run_all.py",
    ROOT / "corpus" / "claims_ledger.py",
    ROOT / "corpus" / "scorecard.py",
]

PROVEN = {"proven_unmatched", "proven", "ProvenUnmatched"}
OPEN = {"open_breaks", "open_break", "open", "OpenBreak"}


def _names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            out.add(child.id)
        elif isinstance(child, ast.Attribute):
            out.add(child.attr)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.add(child.value)
    return out


@pytest.mark.parametrize("path", REPORTING, ids=lambda p: p.name)
def test_no_expression_adds_a_proven_count_to_an_open_count(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} does not exist")
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)):
            continue
        left, right = _names(node.left), _names(node.right)
        if (left & PROVEN and right & OPEN) or (left & OPEN and right & PROVEN):
            raise AssertionError(
                f"{path.name}:{node.lineno} adds a ProvenUnmatched count to an "
                "OpenBreak count. One asserts, the other does not; a total "
                "over both recreates the conflation DECISIONS.md 40 forbids.")


@pytest.mark.parametrize("path", REPORTING, ids=lambda p: p.name)
def test_no_reporting_module_reads_the_legacy_combined_field(path: Path):
    """`correctly_unmatched` is the pre-amendment total and is the easiest way
    to re-merge by accident: it is a single attribute that already holds the
    sum."""
    if not path.exists():
        pytest.skip(f"{path.name} does not exist")
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        hit = (isinstance(node, ast.Attribute) and node.attr == "correctly_unmatched") \
            or (isinstance(node, ast.Constant) and node.value == "correctly_unmatched")
        if hit:
            raise AssertionError(
                f"{path.name}:{node.lineno} reads `correctly_unmatched`, the "
                "pre-amendment combined total. Report `proven_unmatched` and "
                "`open_breaks` separately (DECISIONS.md 40, contract 4.7).")


#: A line may cite the combined figure when it is describing the SUPERSEDED
#: outcome, whose population genuinely was one number. Saying so is the entire
#: point of contract 4.7, and a test that forbade it would forbid the
#: repository from explaining its own history.
HISTORICAL = ("correctlyunmatched", "45.7%", "superseded", "used to",
              "replaced", "pre-amendment", "before the", "old outcome")


def test_the_generated_reports_do_not_print_the_combined_total():
    """The arithmetic check, over the artefacts a reader actually sees.

    The prohibition is on presenting the sum as a CURRENT total. A historical
    citation is allowed and must say what it is on the same line, so that a
    reader meeting the number cannot mistake it for a live figure.
    """
    import json
    results = ROOT / "corpus" / "oracle_results.json"
    if not results.exists():
        pytest.skip("no oracle run on disk")
    payload = json.loads(results.read_text())
    combined = sum(r["measured"]["proven_unmatched"]["rows"]
                   + r["measured"]["open_break"]["rows"] for r in payload)
    renderings = (str(combined), f"{combined:,}")
    offences: list[str] = []
    for report in (ROOT / "corpus" / "ORACLE_RESULTS.md",
                   ROOT / "corpus" / "THREE_SYSTEMS.md",
                   ROOT / "README.md",
                   ROOT / "docs" / "CLAIMS.md",
                   ROOT / "docs" / "SCORECARD.md"):
        if not report.exists():
            continue
        for number, line in enumerate(report.read_text().splitlines(), 1):
            if not any(r in line for r in renderings):
                continue
            if any(marker in line.lower() for marker in HISTORICAL):
                continue
            offences.append(f"{report.name}:{number}: {line.strip()[:120]}")
    assert not offences, (
        f"{combined} is ProvenUnmatched + OpenBreak. These lines present it "
        "without saying it describes the superseded outcome, so a reader "
        "cannot tell it from a live total (DECISIONS.md 40):\n  "
        + "\n  ".join(offences))
