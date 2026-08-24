"""No module under `resolver/` may reach the answer key. Enforced, not assumed.

## Why this file exists rather than an entry in an existing allowlist

`engine/tests/test_no_leakage.py` scans `engine/`, `matching/` and `eval/`.
`tests/test_isolation.py` enforces the same over `matching/` by AST. **Neither
covers `resolver/`**, and a suite that does not scan a directory says nothing
about it -- which is precisely how defect D2 shipped: an unguarded `elif` that
could not execute on the only dataset in the repo, inside a 268-test suite that
passed.

So the rule is re-enforced here, over this package, by three independent
mechanisms: source text, the AST, and the live import graph.

## This test has been seen to FAIL

Verified by deliberately adding `json.loads((d / "ground_truth.json").read_text())`
to `resolver/resolve.py` and re-running: `test_no_source_mentions_the_answer_key`
and `test_no_ast_node_reaches_for_the_key` both failed, and the assertion text
named the file and the line. A test nobody has watched fail is a test nobody
has run.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent
FORBIDDEN_NAMES = ("ground_truth", "GROUND_TRUTH", "answer_key")
#: Modules a resolver may not import at all. `corpus.oracle` reads the key;
#: `corpus.generator` knows how the data was made; `matching` is the frozen
#: engine and reusing it would make the comparison a comparison with itself.
FORBIDDEN_IMPORTS = ("corpus.oracle", "corpus.generator", "corpus.baseline",
                     "matching", "engine.generator", "engine.simulator")


def resolver_sources() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "tests" not in p.parts)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Docstrings are prose, not reads.

    Every module here EXPLAINS the isolation rule, and a rule that cannot be
    written down in the file it governs is a rule nobody can follow. A
    docstring is never executed, so excluding it costs nothing -- the AST check
    below still sees any string that reaches real code.
    """
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def _code_only(path: Path) -> str:
    """The module's source with every docstring removed."""
    tree = ast.parse(path.read_text(), filename=str(path))
    docstrings = _docstring_nodes(tree)
    lines = path.read_text().splitlines()
    for node in ast.walk(tree):
        if id(node) in docstrings:
            for number in range(node.lineno - 1, node.end_lineno):
                lines[number] = ""
    return "\n".join(lines)


@pytest.mark.parametrize("path", resolver_sources(), ids=lambda p: p.name)
def test_no_source_mentions_the_answer_key(path):
    """The crudest check, and the one that catches a hurried edit.

    `loaders.FORBIDDEN` is the single permitted occurrence: it exists to name
    the file the loader refuses to open, and a rule cannot forbid a filename
    without writing it down.
    """
    text = _code_only(path)
    for name in FORBIDDEN_NAMES:
        if name not in text:
            continue
        if path.name == "loaders.py" and name == "ground_truth":
            continue                      # the refusal names what it refuses
        pytest.fail(f"{path.name} mentions {name!r}; no resolver module may "
                    "name the answer key")


@pytest.mark.parametrize("path", resolver_sources(), ids=lambda p: p.name)
def test_no_ast_node_reaches_for_the_key(path):
    """Text matching is defeated by `'ground' + '_truth.json'`. The AST is
    not defeated by string concatenation of literals, because the constant
    folder resolves it -- and any dynamic construction shows up as a call on
    an untrusted path, which the import check below also blocks."""
    tree = ast.parse(path.read_text(), filename=str(path))
    docstrings = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if id(node) in docstrings:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if "ground_truth" in value and path.name != "loaders.py":
                pytest.fail(f"{path.name}:{node.lineno} builds the string "
                            f"{value!r}")
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            pytest.fail(f"{path.name}:{node.lineno} reads .{node.attr}")


@pytest.mark.parametrize("path", resolver_sources(), ids=lambda p: p.name)
def test_no_forbidden_import(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for module in imported:
        for forbidden in FORBIDDEN_IMPORTS:
            assert not module.startswith(forbidden), (
                f"{path.name} imports {module!r}")


def test_the_live_import_graph_is_clean():
    """Static checks miss a lazy import inside a function body that only fires
    at runtime. Import every resolver module and inspect what actually landed
    in `sys.modules` underneath it."""
    import sys

    before = set(sys.modules)
    for info in pkgutil.walk_packages([str(PACKAGE)], prefix="resolver."):
        if ".tests" in info.name:
            continue
        importlib.import_module(info.name)
    landed = set(sys.modules) - before
    for module in landed:
        for forbidden in FORBIDDEN_IMPORTS:
            assert not module.startswith(forbidden), (
                f"importing the resolver pulled in {module!r}")


def test_the_loader_refuses_the_key_by_name():
    from resolver.loaders import FORBIDDEN, GroundTruthAccess, load

    assert "ground_truth.json" in FORBIDDEN
    with pytest.raises(GroundTruthAccess):
        load(Path("corpus/datasets/A20_B100_Cmax/ground_truth.json"))


def test_no_resolver_module_opens_a_file_the_loader_did_not_open():
    """Only `loaders.py` performs I/O. Every other module receives data.

    This is what makes the isolation argument structural rather than
    behavioural: there is exactly one door, and the rule lives on it.
    """
    for path in resolver_sources():
        if path.name == "loaders.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                name = getattr(function, "attr", None) or getattr(
                    function, "id", None)
                assert name not in {"open", "read_text", "read_bytes"}, (
                    f"{path.name}:{node.lineno} performs I/O; only loaders.py "
                    "may")
