"""A truncated collection in a results file must announce its own truncation.

`corpus/score_resolver.py` wrote `report.violations[:12]` with nothing saying
so. At `datasets/A20_Bnone_Cmax` that stored 3 `G8` entries while
`violations_by_gate` correctly recorded 9.

**No published figure was affected** — every gate number in this repository
derives from `violations_by_gate`, which was always complete — so this is a
reporting truncation, not a soundness defect. It is fixed anyway, because a
sample that does not announce itself is the shape of `DECISIONS.md` §39: a
weaker epistemic state presented as a stronger one.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RESULTS = [ROOT / "corpus" / "oracle_results.json",
           ROOT / "corpus" / "oracle_results_run1.json",
           ROOT / "corpus" / "oracle_results_run2.json"]
WRITERS = [ROOT / "corpus" / "score_resolver.py",
           ROOT / "corpus" / "baseline_old_engine.py"]


def test_the_violations_field_declares_whether_it_is_a_sample():
    current = ROOT / "corpus" / "oracle_results.json"
    if not current.exists():
        pytest.skip("no oracle run on disk")
    rows = json.loads(current.read_text())
    for row in rows:
        assert "violations_total" in row and "violations_truncated" in row, (
            f"{row['dataset']}: the `violations` list carries no statement of "
            "whether it is complete. Re-run `python3 "
            "corpus/score_resolver.py --all`; a sample that does not announce "
            "itself is DECISIONS.md 39's shape.")
        stored, total = len(row["violations"]), row["violations_total"]
        assert row["violations_truncated"] == (stored < total), (
            f"{row['dataset']}: violations_truncated="
            f"{row['violations_truncated']} but {stored} of {total} stored")


def test_the_gate_counts_are_complete_even_when_the_sample_is_not():
    """`violations_by_gate` is the authoritative field and must never be a
    sample. This is the check that says no published number was affected."""
    current = ROOT / "corpus" / "oracle_results.json"
    if not current.exists():
        pytest.skip("no oracle run on disk")
    for row in json.loads(current.read_text()):
        by_gate = sum(row["violations_by_gate"].values())
        assert by_gate == row["violations_total"], (
            f"{row['dataset']}: violations_by_gate sums to {by_gate} but the "
            f"report held {row['violations_total']} violations. The gate "
            "counts are what every published figure derives from; if they "
            "are a sample, published numbers ARE affected.")


@pytest.mark.parametrize("path", WRITERS, ids=lambda p: p.name)
def test_no_writer_slices_a_collection_without_flagging_it(path: Path):
    """Static guard.

    A value written into a results dict under key `K` that is built from a
    SLICE must have a `K_truncated` flag somewhere in the same function. The
    flag need not sit in the same dict literal -- nested `detail` blocks are
    flagged by their parent -- but it must exist, and the reader must be able
    to find it.
    """
    if not path.exists():
        pytest.skip(f"{path.name} missing")
    tree = ast.parse(path.read_text())
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        sliced_keys, flag_keys = [], set()
        for node in ast.walk(function):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant)
                        and isinstance(key.value, str)):
                    continue
                if key.value.endswith("_truncated"):
                    flag_keys.add(key.value)
                if any(isinstance(n, ast.Subscript)
                       and isinstance(n.slice, ast.Slice)
                       for n in ast.walk(value)):
                    sliced_keys.append((key.value, key.lineno))
        if sliced_keys:
            assert flag_keys, (
                f"{path.name}: {function.name}() writes sliced collection(s) "
                f"under {[k for k, _ in sliced_keys]} (line "
                f"{sliced_keys[0][1]}) and declares no `*_truncated` flag "
                "anywhere in the function. A sample that does not announce "
                "itself is DECISIONS.md 39's shape.")
