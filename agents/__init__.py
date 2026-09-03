"""Agents that sit downstream of `store`/`service` and narrate, surface, or
draft against real resolver output -- never match, and never write to
`runs`/`line_outcomes`/`row_outcomes`/`break_history` (DECISIONS.md Sec.94,
extending Sec.11's "the LLM narrates and never matches" to this layer).

`tests/test_agent_isolation.py` enforces that no module here imports
`resolver`, `resolver_contract`, `matching`, or `engine` directly -- every
fact an agent needs about a row comes through `store.queries`/`store.approvals`.
"""
