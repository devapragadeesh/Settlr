"""Agent 5 -- drafts an ITC-exposure response for an `OpenBreak` carrying a
real `itc_risk` finding. Best-grounded of the domain agents: `itc_risk`/
`itc_risk_grounds` are real `OpenBreak` fields (`resolver_contract/types.py:
928-937`), populated by `resolver/breaks.py::_itc_risk_months`'s real
`gstr2b.csv` read -- not invented for this agent.

The draft states, every time, the same architectural fact this session's
dashboard GST panel already states: GST evidence (`EvidenceKind.GST_DOCUMENT`)
attests only to `Attests.ROW_EXISTENCE` and can never license a composition
(`resolver/breaks.py:365-370`) -- so a reader cannot mistake an ITC-exposure
draft for a claim about WHICH bank credit the row belongs to. Always requires
approval: this is statutory language with real legal consequences, and
DECISIONS.md Sec.11's "the LLM narrates and never matches" here means Claude
drafts phrasing around facts and a statute citation it is given, never
invents either.
"""

from __future__ import annotations

import sqlite3

from agents.base import ModelUnavailable, call_claude
from store.approvals import create_approval_request
from store.queries import row_outcome

#: Ground -> (statute citation, drafting instruction). Citations match the
#: comments already in `resolver/breaks.py:149-151` -- not invented here.
_GROUNDS = {
    "gstr2b_absent": (
        "Sec 16(2)(aa), CGST Act",
        "Draft an ITC disallowance entry and a one-paragraph email to the "
        "supplier asking whether they filed GSTR-1 for the relevant period. "
        "State the statute plainly. Do not invent a period or GSTIN not given."),
    "gstr2b_no_irn": (
        "Rule 48(5), CGST Rules",
        "Draft an ITC rejection entry and a request to the supplier for a "
        "corrected e-invoice carrying a valid IRN. State the rule plainly. "
        "Do not invent an invoice number not given."),
    "gstr2b_37a_exposure": (
        "Rule 37A, CGST Rules",
        "Draft a Rule 37A reversal note and a GSTR-3B amendment instruction, "
        "using the paise amount and period given. Do not invent an interest "
        "rate or amount not given."),
}

_DISCLAIMER = (
    "This flags input-tax-credit exposure on a row already outside any "
    "matched batch. GST evidence attests only that the invoice exists; it "
    "does not and cannot identify which bank credit this row belongs to."
)


class NoItcRisk(Exception):
    """Raised when the row carries no real `itc_risk` finding to draft against."""


def gather_grounds(conn: sqlite3.Connection, run_id: str, row_id: str) -> dict:
    outcome = row_outcome(conn, run_id, row_id)
    if outcome is None or type(outcome).__name__ != "OpenBreak" or not outcome.itc_risk:
        raise NoItcRisk(f"{row_id} in {run_id} carries no itc_risk finding")
    if row_id not in outcome.itc_risk:
        raise NoItcRisk(f"{row_id} is not among the flagged rows on this break")
    return {"row_id": row_id, "grounds": list(outcome.itc_risk_grounds),
            "age_days": outcome.age_days, "first_seen": outcome.first_seen}


def draft(facts: dict, *, model: str = "claude-sonnet-5") -> dict:
    grounds = facts["grounds"]
    if not grounds:
        raise NoItcRisk("no grounds recorded despite itc_risk being set")
    drafts: dict[str, str] = {}
    for ground in grounds:
        citation, instruction = _GROUNDS.get(
            ground, (ground, "Draft a plain note about this GST finding."))
        try:
            text = call_claude(instruction, str({**facts, "citation": citation}), model=model)
        except ModelUnavailable:
            text = (f"[{citation}] {facts['row_id']}, open {facts['age_days']} days "
                    f"since {facts['first_seen']}. Ground: {ground}.")
        drafts[ground] = f"{text}\n\n{_DISCLAIMER}"
    return drafts


def propose(conn: sqlite3.Connection, run_id: str, row_id: str, *, created_at: str,
            agent: str = "itc_drafter", model: str = "claude-sonnet-5") -> str:
    facts = gather_grounds(conn, run_id, row_id)
    drafts = draft(facts, model=model)
    evidence_summary = "\n\n".join(f"[{g}]\n{text}" for g, text in drafts.items())
    return create_approval_request(
        conn, agent=agent, action="itc_exposure_draft", run_id=run_id,
        row_ids=[row_id], proposed_change={"grounds": facts["grounds"], "drafts": drafts},
        evidence_summary=evidence_summary, created_at=created_at)
