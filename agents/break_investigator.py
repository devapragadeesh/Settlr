"""Agent 3 -- investigates `unexplained` open breaks (1,472 of them on the
30-dataset corpus, the single largest category, per DECISIONS.md Sec.94) and
proposes a reclassification for a human to approve. Absorbs the original
proposal's separate "ERP Gap Resolver": there is no live, separate
`erp_gap_no_order`/`erp_gap_no_payment` reason for that agent to key off (it
belongs to the frozen `matching/` cascade), so ERP-linkage investigation is
one strategy this agent applies, not a second agent.

**What this agent can honestly investigate, and no more.** The original
proposal's steps 1-3 (query the PSP API, scan the bank statement, look up the
ERP order) assume live external-system connectors this repo does not have --
building them now would mean either fabricating a response or depending on
credentials this environment does not hold, which is exactly the discipline
this whole repo is built to refuse. Real external connectors are Phase 3
(`ingest`/`transport` adapters), not this agent. What genuinely IS available,
and real: `resolver/breaks.py:_break_reason` never sets `OpenBreak.warrant`
for any reason (confirmed by reading every `OpenBreak(...)` call site -- only
`ProvenUnmatched` gets one), so there is no evidence to summarize there. What
IS real and useful: `age_days`, `first_seen`, `itc_risk`, and -- the one
genuinely new signal this agent adds -- `row_history` across every run of the
same dataset, which can show a row classified differently under a different
`(cap, time_budget)`, a fact nothing else in this repo surfaces on its own.

Claude's role stays exactly Sec.11's: it drafts the case-file PROSE from
these facts. It never chooses `new_reason` -- that string is always supplied
by the caller (the human, or a future Phase 3 connector that can actually
observe something new), and `propose_reclassification` validates it against
`store.queries.valid_break_reasons()` before it can become a pending request.
"""

from __future__ import annotations

import sqlite3

from agents.base import ModelUnavailable, call_claude
from store.approvals import create_approval_request
from store.queries import get_run, open_break_detail, row_history, valid_break_reasons

_CASE_FILE_INSTRUCTION = (
    "Write a 2-3 sentence case file for a finance analyst about one "
    "unresolved reconciliation break, using ONLY the facts given below. Do "
    "not guess why it is unexplained. If the history shows no variation "
    "across runs, say plainly that nothing distinguishes it."
)


class NotInvestigable(Exception):
    """Raised when the row is not an `unexplained` open break -- this agent
    has nothing else to say about any other reason or disposition."""


def gather_case_facts(conn: sqlite3.Connection, run_id: str, row_id: str) -> dict:
    detail = open_break_detail(conn, run_id, row_id)
    if detail is None or detail["reason"] != "unexplained":
        raise NotInvestigable(
            f"{row_id} in {run_id} is not an unexplained open break")
    run = get_run(conn, run_id)
    if run is None:
        raise KeyError(run_id)
    history = row_history(conn, run["dataset"], row_id)
    distinct_states = {h["state"] for h in history}
    return {
        "row_id": row_id,
        "age_days": detail["age_days"],
        "first_seen": detail["first_seen"],
        "itc_risk_flagged": bool(detail["itc_risk"]),
        "history": history,
        "classified_differently_under_another_run": len(distinct_states) > 1,
    }


def draft_case_file(facts: dict, *, model: str = "claude-sonnet-5") -> str:
    try:
        return call_claude(_CASE_FILE_INSTRUCTION, str(facts), model=model)
    except ModelUnavailable:
        variation = ("classified differently under at least one other run"
                     if facts["classified_differently_under_another_run"]
                     else "classified the same way in every run on record")
        itc_note = " ITC-risk flagged." if facts["itc_risk_flagged"] else ""
        return (f"{facts['row_id']}: unexplained, {facts['age_days']} days open "
                f"since {facts['first_seen']}, {variation}.{itc_note}")


def propose_reclassification(conn: sqlite3.Connection, run_id: str, row_id: str, *,
                              new_reason: str, rationale: str, created_at: str,
                              agent: str = "break_investigator",
                              model: str = "claude-sonnet-5") -> str:
    if new_reason not in valid_break_reasons():
        raise ValueError(f"{new_reason!r} is not a real BreakReason value")
    facts = gather_case_facts(conn, run_id, row_id)
    case_file = draft_case_file(facts, model=model)
    evidence_summary = f"{case_file}\n\nProposed reason: {new_reason}. Rationale: {rationale}"
    return create_approval_request(
        conn, agent=agent, action="reclassify", run_id=run_id, row_ids=[row_id],
        proposed_change={"new_reason": new_reason}, evidence_summary=evidence_summary,
        created_at=created_at)
