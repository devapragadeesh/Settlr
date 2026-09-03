"""Agent 1 -- surfaces carry-forward breaks for the queue view. Rescoped from
the original proposal's "auto-close, zero approval" design (DECISIONS.md
Sec.94): the live resolver has no `is_actionable`/`NOT_A_PROBLEM` analogue --
that vocabulary belongs to the frozen `matching/stage4_exceptions.py`, which
never writes to `store`. The only live no-action route is
`BreakReason.TIMING_DIFFERENCE` -> `"none -- carry forward"`
(`resolver_contract/types.py:585-586`), and even that carries an explicit
contract warning: `OpenBreak.provable_within_window` "must never be promoted
to a permanent proof" (`resolver_contract/types.py:899-902`).

So this agent groups and labels, and writes nothing. If auto-close is ever
built, it is a separate, later decision with its own justification -- not
something this module does by extending its scope quietly.
"""

from __future__ import annotations

import sqlite3

from store.queries import open_breaks


def group_carry_forward(conn: sqlite3.Connection, run_id: str) -> dict:
    """Every open `timing_difference` break for one run, split by whether the
    ledger can currently prove no credit exists within the observed window
    (`provable_within_window`) -- a narrower, temporary claim, never a
    closure signal on its own."""
    buckets = open_breaks(conn, run_id)
    timing_rows = [row for rows in buckets.values() for row in rows
                   if row["reason"] == "timing_difference"]

    provable_within_window: list[dict] = []
    row = conn.execute(
        "SELECT row_id FROM row_outcomes WHERE run_id = ? AND reason = "
        "'timing_difference' AND provable_within_window = 1", (run_id,))
    provable_row_ids = {r["row_id"] for r in row.fetchall()}
    for row in timing_rows:
        if row["row_id"] in provable_row_ids:
            provable_within_window.append(row)

    return {
        "total": len(timing_rows),
        "provable_within_window": provable_within_window,
        "not_provable_within_window": [r for r in timing_rows
                                        if r["row_id"] not in provable_row_ids],
        "note": ("carry-forward, not auto-closed: provable_within_window is a "
                 "narrower claim than a permanent proof and must not be "
                 "treated as one"),
    }
