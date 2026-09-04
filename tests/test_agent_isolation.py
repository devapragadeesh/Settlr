"""`agents/` must never WRITE `import resolver`, `import resolver_contract`,
`import matching`, or `import engine` itself -- and must never reach
`resolver`, `matching`, or `engine` even transitively.

`resolver_contract` is deliberately NOT in the transitive check: `store/`
(which every agent legitimately imports) itself imports
`resolver_contract.types` for real, allowed reasons -- it is store's own
upstream dependency in the layering (`resolver_contract -> resolver ->
ingest/transport -> store -> service -> agents`), same as
`tests/test_layer_isolation.py` never forbids `resolver/` from importing
`resolver_contract` either. What both isolation tests actually guard is a
layer reaching PAST its immediate upstream into something further away --
here, `agents/` reaching into `resolver`/`matching`/`engine` (the algorithmic
packages) rather than stopping at `store`. The per-file AST check below is
stricter than the transitive one on purpose: an agents/ module is never
ALLOWED to write `import resolver_contract` itself, even though the package
is reachable through `store` -- `store.queries.owner_for_reason` exists
specifically so `agents/sla_watchdog.py` never needs
`resolver_contract.types.BREAK_ROUTING` directly. DECISIONS.md Sec.94 is why
this boundary exists: the proposal that motivated `agents/` initially
conflated `resolver_contract`'s live vocabulary with the frozen `matching/`
cascade's, and a module that could import either one to "check" would make
that mistake easy to reintroduce silently.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"
#: What no `agents/` file may ever write as its own import statement.
FORBIDDEN = ("resolver", "resolver_contract", "matching", "engine")
#: What must never be reachable even transitively -- narrower than FORBIDDEN
#: because `store/`'s own legitimate `resolver_contract` dependency would
#: otherwise make this check permanently, uninformatively red.
TRANSITIVELY_FORBIDDEN = ("resolver", "matching", "engine")


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
        for forbidden in TRANSITIVELY_FORBIDDEN:
            assert not (module == forbidden or module.startswith(forbidden + ".")), (
                f"importing agents/ pulled in {module!r}")


def test_resolver_contract_is_legitimately_reachable_only_through_store() -> None:
    """Not a contradiction of the guard above: `resolver_contract` SHOULD
    land in `agents.break_investigator`'s import closure, because
    `store.queries`/`store.approvals` import it directly and every agent
    imports `store`. What the AST test forbids is an `agents/` file writing
    that import ITSELF -- a real, previously-caught false positive: an
    earlier version of the transitive check above flagged this as
    forbidden, which would have made the live-graph test permanently red
    for a legitimate architecture rather than catching a real violation."""
    import agents.break_investigator  # noqa: F401
    import sys
    assert "resolver_contract.types" in sys.modules
    assert "store.queries" in sys.modules


def test_agents_package_exists_so_this_guard_is_not_vacuous() -> None:
    assert AGENTS.is_dir() and any(AGENTS.glob("*.py")), \
        "agents/ does not exist -- this guard is vacuous"
