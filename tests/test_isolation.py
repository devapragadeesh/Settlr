"""Ground-truth isolation is structural, not conventional.

If the solver needed the answers to run, it would not be a solver. This is the
test that makes that a property of the tree rather than a promise.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MATCHING = ROOT / "matching"
EVAL = ROOT / "eval"

FORBIDDEN_TOKENS = ("ground_truth", "GROUND_TRUTH", "ground-truth")


def matching_modules():
    return sorted(MATCHING.rglob("*.py"))


@pytest.mark.parametrize("path", matching_modules(), ids=lambda p: p.name)
def test_no_matching_module_mentions_the_ground_truth(path):
    text = path.read_text()
    for token in FORBIDDEN_TOKENS:
        assert token not in text, f"{path.name} references {token}"


@pytest.mark.parametrize("path", matching_modules(), ids=lambda p: p.name)
def test_no_matching_module_imports_eval_or_engine_internals(path):
    """`eval` holds the key; `engine.generator` and `engine.simulator` built the
    data. Importing either would make solver and generator agree by
    construction instead of by evidence."""
    tree = ast.parse(path.read_text())
    banned = {"eval", "engine", "engine.generator", "engine.simulator",
              "generator", "simulator"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            assert node.module.split(".")[0] not in banned, node.module


def test_no_matching_module_opens_a_path_outside_engine_data():
    for path in matching_modules():
        text = path.read_text()
        if '"engine"' in text or "'engine'" in text:
            assert '"data"' in text or "'data'" in text, path.name


def test_eval_is_the_only_package_that_reads_the_key():
    readers = [p.name for p in EVAL.rglob("*.py") if "ground_truth" in p.read_text()]
    assert "metrics.py" in readers
    assert not [p for p in matching_modules() if "ground_truth" in p.read_text()]


def test_the_cascade_runs_without_the_key_present(tmp_path, monkeypatch):
    """The strongest form of the check: make the key unreadable and run anyway."""
    import eval.metrics as metrics
    from matching import run

    monkeypatch.setattr(metrics, "GROUND_TRUTH", tmp_path / "absent.json")
    result = run()
    assert len(result.matched_row_ids) > 0
    with pytest.raises(FileNotFoundError):
        metrics.load_truth()
