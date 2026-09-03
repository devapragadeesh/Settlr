"""Agent 2 -- nightly aging escalation, notify-only.

Reads `store.queries.open_breaks(conn, run_id)` (real aging data, the same
buckets `resolver/breaks.py` computes) and groups by `reason` and
`age_bucket`, corrected to the LIVE routing in
`resolver_contract.types.BREAK_ROUTING` via `store.queries.owner_for_reason`
-- not the frozen `matching/` module's `finance-ops`/`tax-ops`/`treasury`
labels, which never appear in this pipeline's output (DECISIONS.md Sec.94).

Of the three reasons the live classifier actually produces
(`upstream_unresolved`, `timing_difference`, `unexplained`), only
`upstream_unresolved` and `unexplained` route to an owner worth escalating to
-- `timing_difference` routes to `"none -- carry forward"`, which this agent
treats as nothing to escalate. No write to `store` happens anywhere here.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from agents.base import ModelUnavailable, call_claude
from store.queries import open_breaks, owner_for_reason

#: reason -> {age_bucket: "notify" | "escalate"}. TIMING_DIFFERENCE is
#: deliberately absent: its owner is "none -- carry forward", so there is no
#: one to escalate to.
SLA = {
    "upstream_unresolved": {"0-30": "notify", "31-60": "notify", "61-90": "escalate", "90+": "escalate"},
    "unexplained": {"0-30": "notify", "31-60": "escalate", "61-90": "escalate", "90+": "escalate"},
}

_DRAFT_INSTRUCTION = (
    "Draft a two-sentence escalation message for a finance-ops Slack channel. "
    "State the reason, the age bucket, the row count, and what the owner "
    "should do next (the close condition). Do not invent a deadline or a "
    "dollar amount not given to you."
)


@dataclass(frozen=True)
class Escalation:
    reason: str
    age_bucket: str
    level: str  # "notify" | "escalate"
    owner: str
    close_condition: str
    row_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def count(self) -> int:
        return len(self.row_ids)


def build_escalations(conn: sqlite3.Connection, run_id: str) -> list[Escalation]:
    buckets = open_breaks(conn, run_id)
    escalations: list[Escalation] = []
    for bucket_name, rows in buckets.items():
        by_reason: dict[str, list[str]] = {}
        for row in rows:
            by_reason.setdefault(row["reason"], []).append(row["row_id"])
        for reason, row_ids in by_reason.items():
            level = SLA.get(reason, {}).get(bucket_name)
            if level is None:
                continue
            owner, close_condition = owner_for_reason(reason)
            escalations.append(Escalation(
                reason=reason, age_bucket=bucket_name, level=level, owner=owner,
                close_condition=close_condition, row_ids=tuple(sorted(row_ids))))
    return escalations


def draft_message(escalation: Escalation, *, model: str = "claude-sonnet-5") -> str:
    try:
        return call_claude(_DRAFT_INSTRUCTION, (
            f"reason: {escalation.reason}\nage_bucket: {escalation.age_bucket}\n"
            f"level: {escalation.level}\nowner: {escalation.owner}\n"
            f"close_condition: {escalation.close_condition}\n"
            f"row_count: {escalation.count}"), model=model)
    except ModelUnavailable:
        return (f"[{escalation.level.upper()}] {escalation.count} '{escalation.reason}' "
                f"break(s) in the {escalation.age_bucket}-day bucket, owned by "
                f"{escalation.owner}. Closes when {escalation.close_condition}.")


def run(conn: sqlite3.Connection, run_id: str, *, model: str = "claude-sonnet-5",
        notifier=print) -> list[Escalation]:
    """Builds and delivers every escalation for one run. `notifier` is the
    integration point for a real Slack/email sink -- defaults to `print` so
    this is runnable and testable with no external service configured."""
    escalations = build_escalations(conn, run_id)
    for escalation in escalations:
        notifier(draft_message(escalation, model=model))
    return escalations
