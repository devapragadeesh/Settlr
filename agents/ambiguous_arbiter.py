"""Agent 6 -- presents an `Ambiguous` line's real candidates for a human to
choose from, and records their choice. Never chooses one itself: `Ambiguous`
(`resolver_contract/types.py:767-797`) deliberately has no `decomposition`/
`composition`/`best`/`chosen`/`answer` attribute -- reading any of those
raises `UnrepresentableClaim` by design -- so this agent reads only
`candidate_set.candidates`, `.rank_one` (the resolver's stated PREFERENCE,
never presented here as an assignment), and `.common_rows`.

A human's resolution is written to `human_resolutions`
(`store/schema.sql`), never to `line_outcomes`: the line's own `Ambiguous`
outcome is untouched, forever, because a human breaking a tie the resolver
correctly refused to break does not turn that refusal into a resolver-
corroborated `Verified` (DECISIONS.md Sec.94).
"""

from __future__ import annotations

import sqlite3

from agents.base import ModelUnavailable, call_claude
from store.approvals import record_human_resolution
from store.queries import line_outcome

_COMPARISON_INSTRUCTION = (
    "Write a short comparison of these candidate compositions for a human "
    "who must pick one, using ONLY the row ids and totals given. Do not "
    "recommend one over another beyond noting which the resolver ranked "
    "first, if any -- that is a preference, not an answer."
)


class NotAmbiguous(Exception):
    """Raised when the line is not an `Ambiguous` outcome."""


def _composition_dict(composition) -> dict:
    return {"credit_ids": list(composition.credit_ids),
            "debit_ids": list(composition.debit_ids),
            "credit_total": composition.credit_total,
            "debit_total": composition.debit_total}


def present(conn: sqlite3.Connection, run_id: str, bank_index: int) -> dict:
    outcome = line_outcome(conn, run_id, bank_index)
    if outcome is None or type(outcome).__name__ != "Ambiguous":
        raise NotAmbiguous(f"line {bank_index} in {run_id} is not Ambiguous")

    candidate_set = outcome.candidate_set
    candidates = [_composition_dict(c) for c in candidate_set.candidates]
    rank_one = (_composition_dict(candidate_set.rank_one)
                if candidate_set.rank_one is not None else None)
    return {
        "bank_index": bank_index,
        "candidate_count": candidate_set.size,
        "complete": candidate_set.complete,
        "candidates": candidates,
        "rank_one": rank_one,
        "common_rows": list(outcome.common_rows),
    }


def draft_comparison(presentation: dict, *, model: str = "claude-sonnet-5") -> str:
    try:
        return call_claude(_COMPARISON_INSTRUCTION, str(presentation), model=model)
    except ModelUnavailable:
        lines = [f"{presentation['candidate_count']} candidate(s) explain this credit."]
        for i, candidate in enumerate(presentation["candidates"]):
            lines.append(f"  {i}: credits {candidate['credit_ids']} "
                         f"(total {candidate['credit_total']})")
        if presentation["rank_one"] is not None:
            lines.append("Resolver's stated preference (not an assignment): "
                         f"{presentation['rank_one']['credit_ids']}")
        return "\n".join(lines)


def record_resolution(conn: sqlite3.Connection, run_id: str, bank_index: int, *,
                       chosen_candidate_row_ids: list[str], rationale: str,
                       resolved_by: str, resolved_at: str) -> str:
    presentation = present(conn, run_id, bank_index)
    valid_choices = {
        tuple(sorted(c["credit_ids"] + c["debit_ids"])) for c in presentation["candidates"]
    }
    if tuple(sorted(chosen_candidate_row_ids)) not in valid_choices:
        raise ValueError(
            f"{chosen_candidate_row_ids!r} is not one of the resolver's real "
            f"candidates for line {bank_index}")
    return record_human_resolution(
        conn, run_id=run_id, bank_index=bank_index,
        chosen_candidate_row_ids=chosen_candidate_row_ids, rationale=rationale,
        resolved_by=resolved_by, resolved_at=resolved_at)
