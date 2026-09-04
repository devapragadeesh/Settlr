"""Agent 7 -- natural-language questions over one run's real, already-
persisted output. Claude drafts a single read-only `SELECT` and a plain-
English summary of what it returned; `agents/sql_safety.py` is what actually
lets that be trusted with a live connection. If Claude is unreachable, or the
SQL it drafts is rejected, a small deterministic router answers the handful
of questions `store.queries` can answer directly -- degraded, not silent.
"""

from __future__ import annotations

import re
import sqlite3

from agents.base import ModelUnavailable, call_claude
from agents.sql_safety import UnsafeQuery, safe_select
from store.queries import open_breaks

SCHEMA_DESCRIPTION = """\
Tables you may query with a single SELECT statement:

runs(run_id, dataset, resolver, cap, time_budget, started_at, finished_at, seconds, status)
line_outcomes(run_id, bank_index, kind, reason, pool_size, rival_closure_count,
    rival_count_is_lower_bound, candidate_count, candidate_complete,
    enumeration_cap, nearest_residual, detail)
    -- kind is one of: Verified, AttestationDiscrepancy, Reconstructed, Ambiguous, Unresolved
row_outcomes(run_id, row_id, disposition, reason, age_days, first_seen,
    caused_by, provable_within_window, itc_risk)
    -- disposition is one of: ProvenUnmatched, CorrectlyUnmatched, OpenBreak
    -- reason (only meaningful for OpenBreak) is one of: missing_source,
    -- timing_difference, mapping_issue, unexpected_change, true_error,
    -- upstream_unresolved, unexplained
break_history(row_id, reason, first_run_id, first_seen_at, last_run_id, closed_at, close_run_id)
"""

_SQL_INSTRUCTION = (
    "Given the schema below and a question, write exactly one SQLite SELECT "
    "statement that answers it, scoped to run_id = '{run_id}'. Output ONLY "
    "the SQL, no commentary, no markdown fences.\n\n" + SCHEMA_DESCRIPTION
)

_SUMMARY_INSTRUCTION = (
    "Answer the user's question in one or two plain-English sentences using "
    "ONLY the rows below. If the rows are empty, say so plainly -- do not "
    "guess a number."
)

_FALLBACK_PATTERNS = [
    (re.compile(r"\bopen break", re.I), "open_break_count"),
    (re.compile(r"\bunexplained\b", re.I), "unexplained_count"),
    (re.compile(r"\bunresolved\b", re.I), "unresolved_count"),
]


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    return text.strip().rstrip(";").strip()


class ChatAnswerer:
    name = "chat_answerer"

    def __init__(self, model: str = "claude-sonnet-5") -> None:
        self.model = model

    def ask(self, conn: sqlite3.Connection, run_id: str, question: str) -> dict:
        try:
            sql = _strip_fences(call_claude(
                _SQL_INSTRUCTION.format(run_id=run_id), question, model=self.model))
            rows = safe_select(conn, sql)
        except (ModelUnavailable, UnsafeQuery) as exc:
            return self._fallback(conn, run_id, question, reason=str(exc))

        try:
            answer = call_claude(_SUMMARY_INSTRUCTION,
                                  f"question: {question}\nrows: {rows}", model=self.model)
        except ModelUnavailable:
            answer = f"{len(rows)} row(s) matched." if rows else "No rows matched."
        return {"question": question, "sql": sql, "rows": rows, "answer": answer,
                "mode": "claude"}

    def _fallback(self, conn: sqlite3.Connection, run_id: str, question: str,
                   *, reason: str) -> dict:
        for pattern, kind in _FALLBACK_PATTERNS:
            if pattern.search(question):
                buckets = open_breaks(conn, run_id)
                all_rows = [row for rows in buckets.values() for row in rows]
                if kind == "open_break_count":
                    rows = all_rows
                else:
                    target_reason = kind.removesuffix("_count")
                    rows = [r for r in all_rows if r["reason"] == target_reason]
                return {"question": question, "sql": None, "rows": rows,
                        "answer": f"{len(rows)} row(s), from a live query of "
                                  f"this run's own results.",
                        "mode": "fallback"}
        return {"question": question, "sql": None, "rows": [],
                "answer": "The AI assistant is offline, so I can only answer "
                          "a few questions directly right now -- try asking "
                          "about open breaks, unexplained rows, or unresolved "
                          "rows.",
                "mode": "fallback"}
