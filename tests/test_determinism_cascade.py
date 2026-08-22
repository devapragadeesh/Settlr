"""The pipeline must be deterministic with the LLM stubbed out.

CP-SAT is configured with `num_workers = 1` precisely for this: multi-threaded
search returns whichever solution a race produced first, and an enumeration
order that varies run to run makes a truncated candidate list non-reproducible.
"""

import pytest

from eval.report import fingerprint
from matching import run
from matching.llm import DeterministicExplainer, get_explainer


def test_three_consecutive_runs_are_identical():
    digests = [fingerprint(run()) for _ in range(3)]
    assert len(set(digests)) == 1, "cascade is not deterministic"


def test_the_default_explainer_is_the_deterministic_one():
    assert isinstance(get_explainer(), DeterministicExplainer)
    assert get_explainer().name == "deterministic"


def test_the_llm_is_never_consulted_by_stages_one_to_three():
    """Matching is arithmetic. A model that could influence it would make the
    result non-reproducible and unprovable.

    Checked on the AST, not on prose: the matching stages are allowed to
    DISCUSS explanation in their docstrings, and must not IMPORT or CALL it.
    """
    import ast
    from pathlib import Path

    matching = Path(__file__).resolve().parent.parent / "matching"
    banned_modules = {"llm", "anthropic", "openai"}
    banned_calls = {"explain", "get_explainer", "messages"}

    for name in ("stage1_exact.py", "stage2_fuzzy.py", "stage3_solver.py"):
        tree = ast.parse((matching / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned_modules, (name, alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[-1]
                assert module not in banned_modules, (name, node.module)
                for alias in node.names:
                    assert alias.name not in banned_calls, (name, alias.name)
            elif isinstance(node, ast.Call):
                func = node.func
                target = getattr(func, "attr", None) or getattr(func, "id", None)
                assert target not in banned_calls, (name, target)


def test_a_failing_explainer_cannot_change_what_the_pipeline_decides():
    class Exploding:
        name = "exploding"

        def explain(self, request):
            raise RuntimeError("model unavailable")

    baseline = run()
    with pytest.raises(RuntimeError):
        run(explainer=Exploding())

    # and the classification itself is unchanged when narration is swapped
    class Silent:
        name = "silent"

        def explain(self, request):
            return ""

    quiet = run(explainer=Silent())
    assert [(e.type, e.entity_id, e.owner, e.confidence)
            for e in quiet.stage4.exceptions] == \
           [(e.type, e.entity_id, e.owner, e.confidence)
            for e in baseline.stage4.exceptions]


def test_narration_is_the_only_field_an_explainer_can_touch():
    class Shouty:
        name = "shouty"

        def explain(self, request):
            return "WRONG, MATCH IT TO SOMETHING ELSE"

    result = run(explainer=Shouty())
    assert all(e.narrative == "WRONG, MATCH IT TO SOMETHING ELSE"
               for e in result.stage4.exceptions)
    assert result.balance_violations() == []
    assert len(result.matched_row_ids) == len(run().matched_row_ids)


def test_exception_ordering_is_stable():
    first = [(e.type, e.entity_id) for e in run().stage4.exceptions]
    second = [(e.type, e.entity_id) for e in run().stage4.exceptions]
    assert first == second == sorted(first)


def test_the_claude_adapter_falls_back_rather_than_failing(monkeypatch):
    """An unavailable model must never change what the pipeline decides."""
    from matching.llm import ClaudeExplainer, ExplanationRequest

    explainer = ClaudeExplainer()
    monkeypatch.setattr(
        "matching.llm.ClaudeExplainer.explain",
        lambda self, request: DeterministicExplainer().explain(request))
    text = explainer.explain(ExplanationRequest(
        exception_type="dispute_hold_pending", entity_id="pay_x",
        evidence={"dispute_id": "disp_1", "amount": "100.00"},
        proposed_je=None, owner="disputes-ops"))
    assert "disp_1" in text
