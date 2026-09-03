"""The Claude leg -- narrates, drafts, and (for `chat_answerer.py`) proposes
a read-only query. Never assigns, never classifies a row's `reason`, never
writes to `store` on its own authority.

Deliberately the same integration `matching/llm.py::ClaudeExplainer` already
uses (`anthropic`, `claude-sonnet-5`), not a second, separate LLM dependency:
DECISIONS.md Sec.11's "the LLM narrates and never matches" already has one
adversarially-tested implementation in this repo, and a live API call that
degrades to a deterministic fallback on any failure is exactly that same
argument applied to a downstream layer, not a new risk to justify from
scratch. `anthropic` stays optional (see requirements.txt) so a cold clone
with no key still runs every test via the fallback path.
"""

from __future__ import annotations

BASE_SYSTEM = (
    "You are a reconciliation assistant for a settlement-truth engine. "
    "You explain findings and draft responses from data you are given. "
    "You must NOT invent facts not present in the data given to you. "
    "You must NOT propose or imply a match, composition, or assignment -- "
    "all matching decisions are made by deterministic arithmetic upstream "
    "of you and are final. Be concise."
)


class ModelUnavailable(Exception):
    """Claude could not be reached, or no API key is configured. Callers
    must treat this as "narrate with a template instead", never as a reason
    to guess."""


def call_claude(system: str, user: str, *, model: str = "claude-sonnet-5",
                 max_tokens: int = 400) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise ModelUnavailable("anthropic package not installed") from exc
    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=BASE_SYSTEM + "\n\n" + system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text.strip()
    except Exception as exc:  # noqa: BLE001 -- any failure degrades, never propagates
        raise ModelUnavailable(str(exc)) from exc
