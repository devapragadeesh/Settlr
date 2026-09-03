"""`resolver/` must never import the new ingestion/persistence layers.

Companion to `resolver/tests/test_isolation.py`, which guards `resolver/`
against reaching the answer key. This guards the opposite edge of the same
dependency graph: `ingest/`, `transport/`, `store/` and `service/` sit
strictly DOWNSTREAM of `resolver/` (per the plan's layering:
`resolver_contract -> resolver -> ingest/transport -> store -> service`), so
`resolver/` importing any of them would be a cycle, and a cycle here would
also defeat `resolver/tests/test_isolation.py::test_the_live_import_graph_is_clean`
silently -- a new package pulled in through `resolver/` would not be caught by
that test's own FORBIDDEN_IMPORTS list, because that list does not yet know
these packages exist. This file is that missing coverage, enforced the same
way: source text, AST, and the live import graph.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RESOLVER = ROOT / "resolver"
NEW_LAYERS = ("ingest", "transport", "store", "service")


def resolver_sources() -> list[Path]:
    return sorted(p for p in RESOLVER.rglob("*.py") if "tests" not in p.parts)


@pytest.mark.parametrize("path", resolver_sources(), ids=lambda p: str(p.relative_to(RESOLVER)))
def test_no_resolver_module_imports_a_new_layer(path: Path) -> None:
    tree = ast.parse(path.read_text(), filename=str(path))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for module in imported:
        for forbidden in NEW_LAYERS:
            assert not (module == forbidden or module.startswith(forbidden + ".")), (
                f"{path.relative_to(RESOLVER)} imports {module!r} -- "
                f"resolver/ must never import a downstream layer")


def test_the_live_resolver_import_graph_stays_clean_of_new_layers() -> None:
    import sys

    before = set(sys.modules)
    for info in pkgutil.walk_packages([str(RESOLVER)], prefix="resolver."):
        if ".tests" in info.name:
            continue
        importlib.import_module(info.name)
    landed = set(sys.modules) - before
    for module in landed:
        for forbidden in NEW_LAYERS:
            assert not (module == forbidden or module.startswith(forbidden + ".")), (
                f"importing the resolver pulled in {module!r}")


def test_the_new_layers_exist_so_this_guard_is_not_vacuous() -> None:
    # If none of these packages exist yet, the tests above pass trivially and
    # prove nothing. Once Phase A0 lands `ingest/`, this stops being vacuous
    # for that layer; it stays a live check for the others until they land.
    existing = [name for name in NEW_LAYERS if (ROOT / name).is_dir()]
    assert existing, "none of the new layers exist -- this guard is vacuous"
