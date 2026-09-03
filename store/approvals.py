"""Agent proposals and human resolutions -- `agent_approval_requests` and
`human_resolutions` (`store/schema.sql`, DECISIONS.md Sec.94).

Deliberately separate from `store/writer.py`, whose own docstring scopes it
to "`ResolverOutput` -> SQLite rows" -- a run replay. Nothing here ever
touches `runs`/`line_outcomes`/`row_outcomes`/`break_history`; both tables
below are additive annotations keyed by `run_id`, never edits to a run.
"""

from __future__ import annotations

import json
import sqlite3
import uuid


def create_approval_request(conn: sqlite3.Connection, *, agent: str, action: str,
                             run_id: str, row_ids: list[str], proposed_change: dict,
                             evidence_summary: str, created_at: str) -> str:
    request_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO agent_approval_requests (request_id, agent, action, run_id, "
        "row_ids, proposed_change, evidence_summary, status, created_at) "
        "VALUES (?,?,?,?,?,?,?,'pending',?)",
        (request_id, agent, action, run_id, json.dumps(sorted(row_ids)),
         json.dumps(proposed_change), evidence_summary, created_at))
    conn.commit()
    return request_id


def resolve_approval_request(conn: sqlite3.Connection, request_id: str, *,
                              status: str, resolved_by: str, resolved_at: str) -> None:
    if status not in ("approved", "rejected"):
        raise ValueError(f"status must be 'approved' or 'rejected', got {status!r}")
    existing = conn.execute(
        "SELECT status FROM agent_approval_requests WHERE request_id = ?",
        (request_id,)).fetchone()
    if existing is None:
        raise KeyError(request_id)
    if existing["status"] != "pending":
        raise ValueError(f"request {request_id} is already {existing['status']!r}")
    conn.execute(
        "UPDATE agent_approval_requests SET status = ?, resolved_by = ?, "
        "resolved_at = ? WHERE request_id = ?",
        (status, resolved_by, resolved_at, request_id))
    conn.commit()


def get_approval_request(conn: sqlite3.Connection, request_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM agent_approval_requests WHERE request_id = ?",
        (request_id,)).fetchone()
    if row is None:
        return None
    record = dict(row)
    record["row_ids"] = json.loads(record["row_ids"])
    record["proposed_change"] = json.loads(record["proposed_change"])
    return record


def list_approval_requests(conn: sqlite3.Connection, *, status: str | None = None) -> list[dict]:
    if status is None:
        rows = conn.execute(
            "SELECT * FROM agent_approval_requests ORDER BY created_at").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_approval_requests WHERE status = ? ORDER BY created_at",
            (status,)).fetchall()
    records = []
    for row in rows:
        record = dict(row)
        record["row_ids"] = json.loads(record["row_ids"])
        record["proposed_change"] = json.loads(record["proposed_change"])
        records.append(record)
    return records


def record_human_resolution(conn: sqlite3.Connection, *, run_id: str, bank_index: int,
                             chosen_candidate_row_ids: list[str], rationale: str,
                             resolved_by: str, resolved_at: str) -> str:
    resolution_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO human_resolutions (resolution_id, run_id, bank_index, "
        "chosen_candidate_row_ids, rationale, resolved_by, resolved_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (resolution_id, run_id, bank_index,
         json.dumps(sorted(chosen_candidate_row_ids)), rationale, resolved_by, resolved_at))
    conn.commit()
    return resolution_id


def human_resolution(conn: sqlite3.Connection, run_id: str, bank_index: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM human_resolutions WHERE run_id = ? AND bank_index = ? "
        "ORDER BY resolved_at DESC LIMIT 1", (run_id, bank_index)).fetchone()
    if row is None:
        return None
    record = dict(row)
    record["chosen_candidate_row_ids"] = json.loads(record["chosen_candidate_row_ids"])
    return record
