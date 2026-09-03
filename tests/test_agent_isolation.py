"""`agents/` must never import `resolver`, `resolver_contract`, `matching`,
or `engine` directly.

Companion to `tests/test_layer_isolation.py`, which guards the
resolver/ingest-transport-store-service edge of the same dependency graph.
This guards the next edge downstream: agents sit strictly below `store`/
`service` and must learn every fact about a row through them --
`store.queries.owner_for_reason` exists specifically so `agents/sla_watchdog.py`
never needs `resolver_contract.types.BREAK_ROUTING` itself. DECISIONS.md
Sec.94 is why this boundary exists: the proposal that motivated `agents/`
initially conflated `resolver_contract`'s live vocabulary with the frozen
`matching/` cascade's, and a module that could import either one to "check"
would make that mistake easy to reintroduce silently.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"
FORBIDDEN = ("resolver", "resolver_contract", "matching", "engine")


def agent_sources() -> list[Path]:
    return sorted(p for p in AGENTS.rglob("*.py") if "tests" not in p.parts)


@pytest.mark.parametrize("path", agent_sources(), ids=lambda p: str(p.relative_to(AGENTS)))
def test_no_agent_module_imports_a_forbidden_package(path: Path) -> None:
    tree = ast.parse(path.read_text(), filename=str(path))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for module in imported:
        for forbidden in FORBIDDEN:
            assert not (module == forbidden or module.startswith(forbidden + ".")), (
                f"{path.relative_to(AGENTS)} imports {module!r} -- "
                f"agents/ must learn this through store/service instead")


def test_the_live_agents_import_graph_stays_clean_of_forbidden_packages() -> None:
    import sys

    before = set(sys.modules)
    for info in pkgutil.walk_packages([str(AGENTS)], prefix="agents."):
        if ".tests" in info.name:
            continue
        importlib.import_module(info.name)
    landed = set(sys.modules) - before
    for module in landed:
        for forbidden in FORBIDDEN:
            assert not (module == forbidden or module.startswith(forbidden + ".")), (
                f"importing agents/ pulled in {module!r}")


def test_agents_package_exists_so_this_guard_is_not_vacuous() -> None:
    assert AGENTS.is_dir() and any(AGENTS.glob("*.py")), \
        "agents/ does not exist -- this guard is vacuous"
