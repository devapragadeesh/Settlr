"""No API key is configured in a cold clone or CI -- these tests are the
proof that every agent still runs, degraded but correct, in that state.
"""

from __future__ import annotations

from agents.base import ModelUnavailable, call_claude


def test_call_claude_degrades_to_model_unavailable_with_no_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        result = call_claude("system", "user")
    except ModelUnavailable:
        return
    raise AssertionError(f"expected ModelUnavailable with no API key, got: {result!r}")


def test_a_hostile_client_cannot_raise_anything_but_model_unavailable(monkeypatch) -> None:
    import agents.base as base

    class HostileClient:
        def __init__(self, *a, **k) -> None:
            raise RuntimeError("the model provider is on fire")

    class FakeAnthropic:
        Anthropic = HostileClient

    monkeypatch.setitem(__import__("sys").modules, "anthropic", FakeAnthropic())
    try:
        base.call_claude("system", "user")
        raise AssertionError("expected ModelUnavailable")
    except ModelUnavailable:
        pass
