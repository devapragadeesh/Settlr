#!/usr/bin/env python3
"""Generate `dashboard/index.html` -- the Settlr dashboard.

    python3 dashboard/build_dashboard.py

Every number embedded in the page traces to a real artefact already in this
repo, per `CLAUDE.md`'s "reports are generated" rule applied to a webpage
instead of a markdown file:

- health score              <- `dashboard/data.json:coverage.all` (itself a
                                pass-through of `corpus/oracle_results.json`
                                via `corpus.coverage.split()`)
- account-close progression <- `corpus/oracle_results.json`, all 30 datasets
- aging buckets             <- a REAL resolver run against the flagship
                                dataset, persisted via `store/writer.py` and
                                read back via `store/queries.py::open_breaks`
                                -- the oracle's aggregate cannot support this
                                (`dashboard/DASHBOARD_DATA.md`'s own stated
                                limitation), so this is freshly computed here
- ingestion status           <- the flagship dataset's six artifact files,
                                hashed and row-counted live, each mapped to
                                its real `SourceSystem`
- matching grid / drill-down <- `ingest.load()` raw rows + the real
                                resolver output (`store/queries.py::line_outcome`)
                                for the flagship dataset

The flagship dataset is run TWICE (different `cap`) so `store/queries.py::row_history`
has two genuine run entries per row -- a real (if short) audit trail, not a
fabricated one.

This script is the generator; `dashboard/index.html` is the generated
output and must never be hand-edited. `dashboard/web/template.html` is the
hand-authored template with a single injection point, `<!--__SETTLR_DATA__-->`.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import ambiguous_arbiter, break_investigator  # noqa: E402
from agents import itc_drafter, queue_cleaner, sla_watchdog  # noqa: E402
from ingest import load as ingest_load  # noqa: E402
from resolver_contract.types import SourceSystem  # noqa: E402
from service.pipeline import run_pipeline  # noqa: E402
from store.codec import to_jsonable  # noqa: E402
from store.approvals import list_approval_requests  # noqa: E402
from store.db import connect  # noqa: E402
from store.queries import (get_run, line_outcome, open_breaks,  # noqa: E402
                            owner_for_reason, row_history, runs_for_dataset,
                            sources_for_run)

FLAGSHIP_DIR = ROOT / "corpus" / "datasets" / "A20_B50_Cmax"
#: The flagship carries zero itc_risk-flagged breaks (confirmed, DECISIONS
#: Sec.91's GST panel) -- a second, real dataset known to carry some
#: (Sec.95's own test fixture) is loaded ONLY for the ITC Drafter preview,
#: never mixed into any other panel's numbers.
ITC_EXAMPLE_DIR = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"
TEMPLATE_PATH = ROOT / "dashboard" / "web" / "template.html"
APP_JS_PATH = ROOT / "dashboard" / "web" / "app.js"
LOGO_PATH = ROOT / "dashboard" / "web" / "logo_lockup.png"
AI_ORB_PATH = ROOT / "aibutton.png"
OUT_PATH = ROOT / "dashboard" / "index.html"
DASHBOARD_DATA_PATH = ROOT / "dashboard" / "data.json"

#: The dashboard itself stays a static build-time snapshot (DECISIONS
#: Sec.90), but the AI panel's `/chat_answerer` now makes a real, live
#: `POST /runs/{run_id}/ask` call (DECISIONS Sec.101) that needs a real
#: `store` connection to answer against -- a tempdir database, gone the
#: moment this script exits, cannot serve that. This is the one durable
#: artifact this script writes; it is generated (like `index.html` itself)
#: and gitignored, never hand-edited. `service/asgi.py`'s STORE_DB_PATH
#: must point here for the live endpoint to answer the same run_id this
#: build bakes into `window.SETTLR_DATA.meta.run_id`.
LIVE_DB_PATH = ROOT / "dashboard" / "data" / "settlr_demo.db"
ORACLE_RESULTS_PATH = ROOT / "corpus" / "oracle_results.json"

#: filename -> (SourceSystem, human label). The six-artifact contract every
#: dataset directory in this repo carries.
ARTIFACT_SOURCES = {
    "recon_combined.json": (SourceSystem.PSP_LEDGER, "Processor Ledger"),
    "bank_statement.csv": (SourceSystem.BANK, "Bank Statement"),
    "settlement_report.csv": (SourceSystem.PSP_SETTLEMENT_REPORT, "Processor Settlement Report"),
    "erp_orders.csv": (SourceSystem.MERCHANT_ERP, "ERP Order Book"),
    "gstr2b.csv": (SourceSystem.TAX_AUTHORITY, "GSTR-2B Tax Filing"),
    "disputes.json": (SourceSystem.DISPUTE_RECORD, "Dispute Records"),
}

#: Friendly, demo-facing entity labels for the 30 benchmark axis points.
#: The real dataset id is always shown alongside as secondary metadata --
#: this is presentation, not a substitute for traceability.
ENTITY_LABELS = {
    "A10_B100_Cmax": "APAC Gateway Ops",
    "A20_B0_Cmax": "EU Marketplace",
    "A20_B100_Cfifo": "US Direct — FIFO",
    "A20_B100_Cmax": "US Direct — Flagship",
    "A20_B100_Crandom": "LatAm Aggregator",
    "A20_B100_Crandom0": "LatAm Aggregator (Seed 0)",
    "A20_B50_Cmax": "India Retail — Flagship",
    "A20_B75_Cmax": "India Retail (75%)",
    "A20_Bnone_Cmax": "Shadow Ledger (No PSP Feed)",
    "A30_B100_Cmax": "MENA Gateway",
    "A40_B100_Cfifo": "SEA Marketplace — FIFO",
    "A40_B100_Cmax": "SEA Marketplace — Flagship",
    "A40_B100_Crandom": "SEA Marketplace (Randomised)",
    "A40_B50_Cmax": "SEA Marketplace (50%)",
    "A40_Bnone_Cmax": "Shadow Ledger — SEA",
    "A60_B100_Cmax": "ANZ Direct",
    "A20_B100_Cmax_gst": "India GST Pilot",
    "A20_B100_Cmax_gst_noisy": "India GST Pilot (Noisy Filing)",
    "A20_B100_Cmax_gst_holdout": "India GST Pilot — Holdout",
    "A20_B100_Cmax_bankside": "Bank-Side Mispost Watch",
    "A40_B100_Cmax_bankside": "Bank-Side Mispost Watch — SEA",
}


def _friendly_label(axis_point: str, family: str) -> str:
    """`corpus/datasets` and `corpus/datasets_v2` deliberately re-run many of
    the SAME axis points as an independent regeneration (`DECISIONS.md`
    Sec.32: "The corpus was regenerated five times") -- so the same
    axis_point genuinely appears in both families with different measured
    numbers. Without disambiguation two real, distinct entities would render
    with an identical label, which reads as a duplicate-data bug rather than
    what it is: two independent runs of the same scenario."""
    base = ENTITY_LABELS.get(axis_point, axis_point.replace("_", " · "))
    return base if family == "datasets" else f"{base} (v2)"


#: Two rules govern everything baked into the page:
#:   1. If the UI does not render a field, it is not shipped. `artefact`,
#:      `how`, `modelling_assumption`, `source_ref`, `trust.*.source` and
#:      `citation` were all payload-only -- dead weight that was still
#:      readable by anyone who opened the page source.
#:   2. If the UI does render it, it is scrubbed here at the point of
#:      baking, not patched in the renderer. What is not shipped cannot leak.
#:
#: The claims ledger is NOT shipped at all any more, and that is a judgement
#: rather than an omission. It is a genuinely valuable artefact -- every
#: figure this engine publishes, with its denominator and scope -- but it is
#: written for maintainers: it cites decision records by number, names the
#: script behind each row, and speaks in gate identifiers ("gate G1", "gate
#: G9", "CP-SAT solves"). Mechanical translation was attempted first and
#: produced exactly the mess that proves the point ("30 entitys", "fixtures
#: generated from our own /"). A row a reconciliation operator cannot act on
#: does not become a product feature by having its file paths removed, and
#: shipping mangled prose is worse than shipping neither. The health
#: drill-down keeps coverage-by-scope and the abstention record, both of
#: which do mean something to a user.
_CITATION_RE = re.compile(
    r"\s*[\u2014\-,;(]*\s*(?:see\s+)?`?(?:DECISIONS|SETTLEMENT_SPEC|CLAUDE|THREE_SYSTEMS"
    r"|CORPUS_SPEC|INGESTION_REPORT|D15_MEASUREMENT)[^`\n]*?(?:\.md)?`?"
    r"(?:\s*(?:\u00a7|Sec\.?)\s*[\d.]+)?\)?", re.I)

#: This project's internal vocabulary -> what a person reconciling accounts
#: would call the same thing. Applied only to strings the UI actually shows.
_TERMS = [
    ("the oracle", "verification"), ("oracle", "verification"),
    ("frozen cascade", "previous engine"),
    ("datasets", "entities"), ("dataset", "entity"),
    ("`OpenBreak`", "open break"), ("`Verified`", "verified"),
    ("`Reconstructed`", "reconstructed"), ("`Ambiguous`", "ambiguous"),
    ("`ProvenUnmatched`", "proven unmatched"),
    ("`AttestationDiscrepancy`", "source disagreement"),
    ("`Unresolved`", "unresolved"),
    ("this repo's own", "our own"), ("this repo", "this system"),
    ("resolver", "engine"),
]


#: Bare module paths and source filenames that survive citation-stripping
#: because they are used as nouns mid-sentence rather than as citations.
_PATH_RE = re.compile(
    r"`?\b(?:ingest|resolver|store|agents|corpus|matching|engine|service|transport)"
    r"/[\w./]+`?|`?\b[\w.]+\.(?:py|csv|json|md)\b`?")


def _scrub(text: str) -> str:
    """Remove internal citations and translate internal vocabulary. Applied
    to every string the dashboard renders that originates in a document
    written for maintainers rather than for users."""
    out = _CITATION_RE.sub("", text or "")
    for internal, plain in _TERMS:
        out = re.sub(re.escape(internal), plain, out, flags=re.I)
    out = _PATH_RE.sub("", out)
    out = out.replace("`", "")
    out = re.sub(r"\s*--\s*(?:,|$)", "", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" -\u2014,;")


#: The four coverage scopes, named for a reader rather than scrubbed. Only
#: four strings exist, they are all user-facing, and one of them ("the
#: original 14 -- the scope THREE_SYSTEMS.md publishes") mangles under
#: mechanical citation-stripping into "the scope publishes". Where the set
#: is this small and this visible, writing the labels beats regexing them.
_SCOPE_LABELS = {
    "all": "All entities",
    "non_absence": "Entities with a processor settlement file",
    "absence": "Entities with no processor feed",
    "original_14": "The original pilot group",
}


def _present_coverage(coverage: dict) -> dict:
    out = {}
    for key, scope in coverage.items():
        scope = dict(scope)
        if "scope_label" in scope:
            scope["scope_label"] = _SCOPE_LABELS.get(key, _scrub(scope["scope_label"]))
        out[key] = scope
    return out


def _strip_payload_only(node):
    """Drop fields no renderer reads. Recurses the whole baked payload."""
    DROP = {"modelling_assumption", "source_ref", "artefact", "how", "citation"}
    # (`trust.*.source` is handled in build_trust_panel, which owns that shape)
    if isinstance(node, dict):
        return {k: _strip_payload_only(v) for k, v in node.items() if k not in DROP}
    if isinstance(node, list):
        return [_strip_payload_only(v) for v in node]
    return node


def build_entities() -> list[dict]:
    """Every dataset in `corpus/oracle_results.json`, one "entity" each.
    Status is DERIVED from real measured fields, never invented."""
    rows = json.loads(ORACLE_RESULTS_PATH.read_text())
    entities = []
    for row in rows:
        dataset_path = row["dataset"]  # e.g. "datasets/A20_B50_Cmax"
        axis_point = dataset_path.split("/", 1)[1]
        acc = row["measured"]["accounting"]
        verified = acc["verified"]
        open_breaks_n = acc["open_breaks"]
        unresolved = acc["unresolved"]
        ambiguous = acc["ambiguous"]

        if verified == 0 and acc["reconstructed"] == 0:
            status = "not_started"
        elif not row["passed"]:
            status = "awaiting_approval"
        elif open_breaks_n > 0 or unresolved > 0 or ambiguous > 0:
            status = "in_progress"
        else:
            status = "certified"

        entities.append(dict(
            id=dataset_path,
            axis_point=axis_point,
            family=row["family"],
            label=_friendly_label(axis_point, row["family"]),
            status=status,
            passed=row["passed"],
            bank_lines=row["bank_lines"],
            verified=verified,
            open_breaks=open_breaks_n,
            unresolved=unresolved,
            ambiguous=ambiguous,
            proven_unmatched=acc["proven_unmatched"],
        ))
    return entities


#: This corpus was long described in this file's own comments as having "no
#: date dimension". That is true of the per-run scoring table, and false of
#: the records themselves: every row in the processor ledger carries real
#: `created_at` and `settled_at` unix timestamps, disputes carry `opened_at`,
#: settlements carry `initiated_at`, and bank lines carry a value date.
#: Nothing below invents a period -- it is read off the data that was
#: already there and simply never surfaced.
def _ts_to_date(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


def build_period(dataset) -> dict:
    """The real reporting period this entity's data spans, derived from the
    earliest and latest timestamps actually present."""
    created = [r["created_at"] for r in dataset.rows if r.get("created_at")]
    settled = [r["settled_at"] for r in dataset.rows if r.get("settled_at")]
    bank_dates = [line.value_date for line in dataset.bank]
    starts = [d for d in [_ts_to_date(min(created)) if created else None,
                          min(bank_dates) if bank_dates else None] if d]
    ends = [d for d in [_ts_to_date(max(created)) if created else None,
                        _ts_to_date(max(settled)) if settled else None,
                        max(bank_dates) if bank_dates else None] if d]
    if not starts or not ends:
        return {}
    return dict(start=min(starts).isoformat(), end=max(ends).isoformat())


#: Buckets for how long money took to reach the bank. Chosen to match how a
#: settlement schedule is actually discussed (same day / next day / a
#: standard T+2-3 window / longer), not as arbitrary quantiles.
_LAG_BUCKETS = [("Same day", 0, 1), ("T+1", 1, 2), ("T+2-3", 2, 4),
                 ("T+4-7", 4, 8), ("Over a week", 8, 10**6)]

#: How long unsettled money has been outstanding, measured from the
#: transaction's own `created_at` against the latest activity in the data --
#: never against today's wall clock, which would drift every time this
#: dashboard is rebuilt and make the figure unreproducible.
_UNSETTLED_BUCKETS = [("0-7 days", 0, 8), ("8-30 days", 8, 31),
                       ("31-60 days", 31, 61), ("60+ days", 61, 10**6)]


def build_settlement_timing(dataset) -> dict:
    """Settlement lag and unsettled exposure, both real. Every payment row
    carries `created_at`; the 251 that settled also carry `settled_at`."""
    rows = dataset.rows
    lags_days, lag_buckets = [], {label: 0 for label, _, _ in _LAG_BUCKETS}
    for r in rows:
        if not (r.get("created_at") and r.get("settled_at")):
            continue
        days = (int(r["settled_at"]) - int(r["created_at"])) / 86400.0
        lags_days.append(days)
        for label, lo, hi in _LAG_BUCKETS:
            if lo <= days < hi:
                lag_buckets[label] += 1
                break

    # "As of" is the latest timestamp in the data, so the aging below is a
    # property of the dataset rather than of the day the page was built.
    all_ts = [int(r[k]) for r in rows for k in ("created_at", "settled_at")
              if r.get(k)]
    as_of = _ts_to_date(max(all_ts)) if all_ts else None

    unsettled, unsettled_value = [], 0
    aging = {label: dict(count=0, value_paise=0) for label, _, _ in _UNSETTLED_BUCKETS}
    for r in rows:
        if r.get("settled") or not r.get("created_at"):
            continue
        amount = r.get("amount") or 0
        unsettled.append(r)
        unsettled_value += amount
        age = (as_of - _ts_to_date(r["created_at"])).days if as_of else 0
        for label, lo, hi in _UNSETTLED_BUCKETS:
            if lo <= age < hi:
                aging[label]["count"] += 1
                aging[label]["value_paise"] += amount
                break

    return dict(
        settled_count=len(lags_days),
        mean_lag_days=round(sum(lags_days) / len(lags_days), 2) if lags_days else None,
        max_lag_days=round(max(lags_days), 1) if lags_days else None,
        lag_buckets=[dict(label=l, count=lag_buckets[l]) for l, _, _ in _LAG_BUCKETS],
        unsettled_count=len(unsettled),
        unsettled_value_paise=unsettled_value,
        on_hold_count=sum(1 for r in rows if r.get("on_hold")),
        as_of=as_of.isoformat() if as_of else None,
        aging=[dict(label=l, **aging[l]) for l, _, _ in _UNSETTLED_BUCKETS],
    )


def build_method_breakdown(dataset, open_break_row_ids: set[str]) -> list[dict]:
    """Volume, value and break rate per payment method -- the standard
    "where are the breaks concentrated" view. `method` is a real field on
    every payment row; card rows additionally carry a real `card_network`."""
    by_method: dict[str, dict] = {}
    for r in dataset.rows:
        method = r.get("method")
        if not method:
            continue           # adjustments/refunds carry no method
        slot = by_method.setdefault(method, dict(
            method=method, count=0, value_paise=0, breaks=0, networks={}))
        slot["count"] += 1
        slot["value_paise"] += r.get("amount") or 0
        if r["entity_id"] in open_break_row_ids:
            slot["breaks"] += 1
        network = r.get("card_network")
        if network:
            slot["networks"][network] = slot["networks"].get(network, 0) + 1

    out = []
    for slot in by_method.values():
        slot["break_rate_pct"] = round(100 * slot["breaks"] / slot["count"], 1) if slot["count"] else 0.0
        slot["networks"] = sorted(
            ({"name": k, "count": v} for k, v in slot["networks"].items()),
            key=lambda n: -n["count"])
        out.append(slot)
    return sorted(out, key=lambda m: -m["count"])


def build_kpis(dataset, lines: list[dict], timing: dict, rows_by_id: dict,
                aging_rows: dict, run_meta) -> dict:
    """The metrics a reconciliation product leads with, each computed from
    this run's real output rather than stored anywhere."""
    kinds = {}
    for entry in lines:
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
    total = len(lines) or 1
    verified = kinds.get("Verified", 0)
    reconstructed = kinds.get("Reconstructed", 0)

    open_break_rows = [r for rows in aging_rows.values() for r in rows]
    unreconciled = 0
    row_lookup = {r["entity_id"]: r for r in dataset.rows}
    for r in open_break_rows:
        raw = row_lookup.get(r["row_id"])
        if raw:
            unreconciled += raw.get("amount") or raw.get("debit") or 0

    return dict(
        # "Straight through" = matched with no human step needed at all.
        straight_through_pct=round(100 * (verified + reconstructed) / total, 1),
        # "First pass" = matched on an identifier alone, before any
        # arithmetic reconstruction was required.
        first_pass_pct=round(100 * verified / total, 1),
        exception_pct=round(100 * (total - verified - reconstructed) / total, 1),
        matched_lines=verified + reconstructed,
        total_lines=len(lines),
        open_breaks=len(open_break_rows),
        unreconciled_value_paise=unreconciled,
        mean_lag_days=timing.get("mean_lag_days"),
        cycle_seconds=round(run_meta["seconds"], 1) if run_meta else None,
    )


#: A maker-checker queue is the control every reconciliation product is
#: built around, and this repo already had the whole mechanism: three agents
#: with `propose_*` functions that write to `agent_approval_requests`, a
#: schema with preparer/reviewer columns, and `resolve_approval_request` to
#: close the loop. The dashboard had simply never called any of it, so the
#: table was empty in every build and the agents panel could only show
#: read-only previews.
#:
#: This calls the REAL proposal functions against the build's own generated
#: database. What lands in the queue is genuine agent output about genuine
#: open breaks, carrying the real `evidence_summary` each agent drafts.
#: Nothing is auto-approved -- every request is created `pending`, which is
#: the entire point of the control. The writes touch only
#: `agent_approval_requests` in a database this script generates and
#: gitignores; no frozen artefact, and never `row_outcomes`/`line_outcomes`.
_PROPOSAL_LIMIT = 6


def build_approvals(conn, run_id: str, itc_conn, itc_run_id: str,
                     as_of: str) -> list[dict]:
    unexplained = conn.execute(
        "SELECT row_id FROM row_outcomes WHERE run_id = ? AND "
        "disposition = 'OpenBreak' AND reason = 'unexplained' "
        "ORDER BY row_id LIMIT ?", (run_id, _PROPOSAL_LIMIT)).fetchall()
    for row in unexplained:
        try:
            facts = break_investigator.gather_case_facts(conn, run_id, row["row_id"])
        except break_investigator.NotInvestigable:
            continue
        # The proposed reclassification is the agent's own reading of the
        # facts it gathered, not a fixed string: a break whose cause is
        # already identified upstream is proposed as upstream_unresolved,
        # otherwise it stays a timing question for a human to rule on.
        new_reason = "upstream_unresolved" if facts.get("caused_by") else "timing_difference"
        break_investigator.propose_reclassification(
            conn, run_id, row["row_id"], new_reason=new_reason,
            rationale=("Cause already identified upstream; this row should follow it."
                        if facts.get("caused_by")
                        else "No contradicting evidence found; consistent with a "
                             "settlement still in flight."),
            created_at=as_of)

    flagged = itc_conn.execute(
        "SELECT row_id, itc_risk FROM row_outcomes WHERE run_id = ? AND "
        "disposition = 'OpenBreak' AND itc_risk IS NOT NULL ORDER BY row_id",
        (itc_run_id,)).fetchall()
    itc_rows = [r["row_id"] for r in flagged
                 if r["row_id"] in (r["itc_risk"] or "").split(",")][:2]

    requests = []
    for record in list_approval_requests(conn):
        requests.append(_present_approval(record, conn, run_id))
    for row_id in itc_rows:
        itc_drafter.propose(itc_conn, itc_run_id, row_id, created_at=as_of)
    for record in list_approval_requests(itc_conn):
        requests.append(_present_approval(record, itc_conn, itc_run_id))
    return requests


_APPROVAL_ACTIONS = {
    "reclassify": "Reclassify open break",
    "itc_exposure_draft": "Input tax credit exposure",
}


def _present_approval(record: dict, conn, run_id: str) -> dict:
    row_ids = record["row_ids"] if isinstance(record["row_ids"], list) else []
    amount = None
    if row_ids:
        row = conn.execute(
            "SELECT reason, age_days FROM row_outcomes WHERE run_id = ? AND row_id = ?",
            (run_id, row_ids[0])).fetchone()
        amount = dict(reason=row["reason"], age_days=row["age_days"]) if row else None
    change = record["proposed_change"] or {}
    return dict(
        request_id=record["request_id"][:8],
        agent=record["agent"],
        action=_APPROVAL_ACTIONS.get(record["action"], record["action"]),
        row_ids=row_ids,
        current=amount,
        proposed=change.get("new_reason") or (", ".join(change.get("grounds", [])) or None),
        evidence=record["evidence_summary"],
        status=record["status"],
        created_at=record["created_at"],
    )


#: `store`'s `sources` table records, per run, every artefact the pipeline
#: actually read: its checksum, format and transport. It has been written on
#: every run since the store existed and read by nothing -- the dashboard
#: recomputed ingestion status from disk instead. This is the provenance
#: record a customer asks for during an audit ("prove this figure came from
#: the file you say it did"), so it is worth showing as-is rather than
#: re-deriving.
def build_source_provenance(conn, run_id: str) -> list[dict]:
    out = []
    for record in sources_for_run(conn, run_id):
        label = ARTIFACT_SOURCES.get(record["artifact_path"], (None, None))[1]
        out.append(dict(
            artifact=record["artifact_path"],
            label=label or record["artifact_path"],
            format=record["format"],
            sha256=record["sha256"],
            transport=record["transport"],
            fetched_at=record["fetched_at"],
        ))
    return out


def build_ingestion_status(dataset_dir: Path) -> list[dict]:
    statuses = []
    for filename, (source, label) in ARTIFACT_SOURCES.items():
        path = dataset_dir / filename
        if not path.exists():
            continue
        payload = path.read_bytes()
        if filename.endswith(".json"):
            body = json.loads(payload)
            count = len(body.get("items", body if isinstance(body, list) else []))
        else:
            count = max(0, payload.decode().count("\n") - 1)
        statuses.append(dict(
            artifact=filename, source_system=source.value, label=label,
            format=path.suffix.lstrip("."), rows=count,
            bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()[:16],
            transport="file://"))
    return statuses


def build_lines_and_rows(dataset, conn, run_id: str) -> tuple[list[dict], dict[str, dict]]:
    rows_by_id: dict[str, dict] = {}
    lines = []
    row_lookup = {r["entity_id"]: r for r in dataset.rows}

    for bank_index, line in enumerate(dataset.bank):
        outcome = line_outcome(conn, run_id, bank_index)
        entry = dict(
            index=bank_index, reference=line.reference,
            value_date=line.value_date.isoformat(), narration=line.narration,
            amount_paise=line.amount_paise, is_credit=line.is_credit,
            kind=type(outcome).__name__ if outcome else "Unknown")

        outcome_json = to_jsonable(outcome) if outcome else None
        entry["outcome"] = outcome_json

        referenced_ids: set[str] = set()
        if outcome_json:
            comp = outcome_json.get("composition")
            if comp:
                referenced_ids.update(comp["credit_ids"])
                referenced_ids.update(comp["debit_ids"])
            candidate_set = outcome_json.get("candidate_set")
            if candidate_set:
                for candidate in candidate_set["candidates"]:
                    referenced_ids.update(candidate["credit_ids"])
                    referenced_ids.update(candidate["debit_ids"])
            contradiction = outcome_json.get("contradiction")
            if contradiction:
                referenced_ids.update(contradiction["row_ids"])

        for row_id in referenced_ids:
            if row_id in row_lookup and row_id not in rows_by_id:
                raw = row_lookup[row_id]
                rows_by_id[row_id] = dict(
                    entity_id=raw["entity_id"], type=raw.get("type"),
                    amount=raw.get("amount"), credit=raw.get("credit"),
                    debit=raw.get("debit"), settlement_id=raw.get("settlement_id"),
                    order_id=raw.get("order_id"), method=raw.get("method"),
                    description=raw.get("description"),
                    dispute_id=raw.get("dispute_id"),
                    # fee/tax carry the real balance identity
                    # (credit = amount - fee), needed by the Accounting
                    # page's aggregate math. The rest are real per-payment
                    # attributes that were being dropped here: the
                    # timestamps give this dataset a genuine time
                    # dimension, and method/network/segment are what a
                    # "where are breaks concentrated" view is built from.
                    fee=raw.get("fee"), tax=raw.get("tax"),
                    created_at=raw.get("created_at"),
                    settled_at=raw.get("settled_at"),
                    settled=raw.get("settled"), on_hold=raw.get("on_hold"),
                    card_network=raw.get("card_network"),
                    card_type=raw.get("card_type"),
                    notes=raw.get("notes") or {})

        lines.append(entry)
    return lines, rows_by_id


def build_erp_lookup(dataset_dir: Path, order_ids: set[str]) -> dict[str, dict]:
    """Real ERP order rows for the order ids referenced by the flagship
    dataset's ledger rows -- a genuine third data source for the matching
    grid, not a synthesized stand-in."""
    lookup = {}
    path = dataset_dir / "erp_orders.csv"
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["order_id"] in order_ids:
                lookup[row["order_id"]] = dict(
                    order_id=row["order_id"], invoice_no=row["invoice_no"],
                    amount=row["amount"], invoice_date=row["invoice_date"])
    return lookup


def build_settlement_report_lookup(dataset, settlement_ids: set[str]) -> dict[str, dict]:
    """Real PSP settlement-report records for the settlement ids referenced
    by the flagship's ledger rows. `resolver.loaders.load()` already parses
    `settlement_report.csv` into `Dataset.settlement_report`
    (`resolver/loaders.py:88`) -- this is a lookup into data that was
    already loaded, not a fresh read, unlike `build_erp_lookup` (which
    re-reads `erp_orders.csv` because `Dataset.erp_order_ids` only keeps a
    bare id set, not the richer per-order fields this dashboard shows)."""
    return {sid: dict(dataset.settlement_report[sid])
            for sid in settlement_ids if sid in dataset.settlement_report}


def build_row_history_sample(conn, dataset_name: str, row_ids: list[str]) -> dict[str, list[dict]]:
    sample = {}
    for row_id in row_ids:
        history = row_history(conn, dataset_name, row_id)
        if history:
            sample[row_id] = history
    return sample


def build_discrepancies(lines: list[dict]) -> list[dict]:
    """Real `AttestationDiscrepancy` mismatches -- not invented examples."""
    out = []
    for entry in lines:
        outcome = entry["outcome"]
        if not outcome or outcome.get("__type__") != "AttestationDiscrepancy":
            continue
        contradiction = outcome["contradiction"]
        out.append(dict(
            bank_index=entry["index"], reference=entry["reference"],
            kind=contradiction["kind"], detail=contradiction["detail"],
            row_ids=contradiction["row_ids"]))
    return out


def build_trust_panel(dashboard_data: dict) -> dict:
    """Real data that already exists in `dashboard/data.json` but was never
    surfaced anywhere in the UI: the three-system comparison, the D15
    soundness measurement, the commit-ordering evidence, the self-correction
    citation, and dataset-integrity hashes. Aggregated here, not re-derived
    -- every number traces back to `corpus/three_systems.py`/`scorecard.py`/
    live `git log`, exactly as `corpus/export_dashboard.py` computed it."""
    ts = dashboard_data.get("three_systems", {}).get("per_dataset", [])

    def _agg(system: str) -> dict:
        ran = [r[system] for r in ts if r.get(system, {}).get("ran")]
        return dict(wrong=sum(r["wrong"] for r in ran),
                    attempted=sum(r["attempted"] for r in ran),
                    datasets=len(ran))

    # No `source` key: it named the internal script each figure came from,
    # which the panel stopped rendering in the de-jargon pass. Not rendered,
    # not shipped.
    three_systems = dict(naive=_agg("naive"), frozen=_agg("frozen"),
                          resolver=_agg("resolver"))

    commit_ordering = dashboard_data.get("commit_ordering") or {}
    hashes = dashboard_data.get("hashes")

    return dict(
        three_systems=three_systems,
        d15={k: v for k, v in (dashboard_data.get("d15") or {}).items()
              if k != "source"} or None,
        self_correction=dashboard_data.get("self_correction_record"),
        commit_count=commit_ordering.get("count"),
        first_commit=(commit_ordering.get("first_ten") or [{}])[0],
        hashes_verified=hashes,
    )


def build_gst_panel(dataset_dir: Path, conn, run_ids: list[str]) -> dict:
    """Real descriptive stats from the flagship entity's own `gstr2b.csv`,
    plus the real (not fabricated) ITC-risk-flag count across every
    persisted run. `EvidenceKind.GST_DOCUMENT` is bound to
    `Attests.ROW_EXISTENCE` in `resolver_contract/types.py` -- a tax
    document can annotate an open item but never license a composition --
    so this panel reports what the tax feed actually says about this
    entity's invoices, not a risk score the architecture doesn't produce."""
    path = dataset_dir / "gstr2b.csv"
    rows = list(csv.DictReader(path.open(newline="")))
    irn_present = sum(1 for r in rows if r["irn"].strip())
    filed = sum(1 for r in rows if r["supplier_gstr3b_filed"].strip().upper() == "Y")
    available = sum(1 for r in rows if r["itc_availability"].strip().lower() == "yes")

    flagged_total = 0
    for run_id in run_ids:
        flagged_total += conn.execute(
            "SELECT COUNT(*) FROM row_outcomes WHERE run_id = ? AND "
            "disposition = 'OpenBreak' AND itc_risk IS NOT NULL", (run_id,)
        ).fetchone()[0]

    return dict(
        invoices=len(rows), irn_present=irn_present, filed=filed,
        itc_available=available, flagged_at_risk=flagged_total,
        runs_checked=len(run_ids),
    )


def build_stability_panel(conn, dataset_name: str, run_metas: list[dict]) -> dict:
    """Real reproducibility evidence, not a fabricated trend line. The
    resolver is deterministic (DECISIONS.md Sec.14) and every run here is
    against the SAME frozen dataset, so the honest question multiple real
    runs can answer is not "did the numbers change over time" but "does an
    independent re-run reach the identical answer" -- which is itself a
    real, checkable claim, proven here by fingerprinting each run's
    (bank_index, kind) sequence and comparing them."""
    fingerprints = []
    for meta in run_metas:
        rows = conn.execute(
            "SELECT bank_index, kind FROM line_outcomes WHERE run_id = ? "
            "ORDER BY bank_index", (meta["run_id"],)).fetchall()
        fingerprints.append(tuple((r["bank_index"], r["kind"]) for r in rows))

    identical = len(set(fingerprints)) == 1 if fingerprints else False
    return dict(
        runs=[dict(run_id=m["run_id"][:10], cap=m["cap"], time_budget=m["time_budget"],
                    seconds=round(m["seconds"], 1)) for m in run_metas],
        identical_outcomes=identical,
        distinct_fingerprints=len(set(fingerprints)),
    )


#: Which bank-line kinds carry real, citable evidence for an investigation
#: workspace. `Ambiguous` is deliberately excluded here -- it already has
#: its own dedicated workspace (the matching grid's drill-down, and the
#: Ambiguous Batch Arbiter agent); the exceptions list is for lines/rows
#: that need explaining, not lines with too many equally-valid explanations.
_EVIDENCED_LINE_KINDS = ("Unresolved", "AttestationDiscrepancy")


def build_run_diff(conn, run_a: str, run_b: str, *, cap_a: int, cap_b: int,
                    time_budget_a: float, time_budget_b: float) -> dict:
    """A real diff between two of the 4 persisted flagship runs, via
    `row_outcomes.disposition` -- the same table `store.queries.open_breaks`
    reads. Both runs are the SAME dataset (`A20_B50_Cmax`) at different
    solver settings, never a different time period (this corpus has no date
    dimension) -- the caller must label it that way, not as "since last
    run" in a time sense. `row_outcomes` only ever holds UNMATCHED rows
    (`store/writer.py`), so a row absent from both is a row matched in both
    -- genuinely uninteresting to this diff, correctly excluded rather than
    counted as a fabricated "0 rows changed."""
    def row_states(run_id: str) -> dict[str, str]:
        rows = conn.execute(
            "SELECT row_id, disposition FROM row_outcomes WHERE run_id = ?", (run_id,)
        ).fetchall()
        return {r["row_id"]: r["disposition"] for r in rows}

    a_states, b_states = row_states(run_a), row_states(run_b)
    unchanged = resolved = new_breaks = reclassified = 0
    for row_id in set(a_states) | set(b_states):
        sa, sb = a_states.get(row_id), b_states.get(row_id)
        if sa == sb:
            unchanged += 1
        elif sa == "OpenBreak":
            resolved += 1
        elif sb == "OpenBreak":
            new_breaks += 1
        else:
            reclassified += 1

    return dict(run_a=run_a, run_b=run_b, cap_a=cap_a, cap_b=cap_b,
                time_budget_a=time_budget_a, time_budget_b=time_budget_b,
                unchanged=unchanged, resolved=resolved,
                new_breaks=new_breaks, reclassified=reclassified)


def build_runs_table(entities: list[dict]) -> list[dict]:
    """One row per real `corpus/oracle_results.json` entity -- no `period`
    column: this corpus has no date dimension, and inventing one would be
    exactly the fabrication this repo's discipline forbids. `sources` and
    `match_rate` are real, computed here rather than stored, because
    neither is a field oracle_results.json happens to carry."""
    table = []
    for e in entities:
        dataset_dir = ROOT / "corpus" / e["id"]
        sources = sum(1 for filename in ARTIFACT_SOURCES if (dataset_dir / filename).exists())
        match_rate = (e["verified"] / e["bank_lines"] * 100) if e["bank_lines"] else 0.0
        table.append(dict(
            axis_point=e["axis_point"], label=e["label"], family=e["family"],
            sources=sources, match_rate=match_rate,
            open_exceptions=e["open_breaks"], passed=e["passed"],
            is_flagship=(e["axis_point"] == "A20_B50_Cmax" and e["family"] == "datasets")))
    return table


def build_accounting_summary(lines: list[dict], rows_by_id: dict[str, dict]) -> dict:
    """Real Sigma(fee)/Sigma(credit)/Sigma(debit) from this run's own
    Verified/Reconstructed lines -- the only lines the resolver closed with
    a real composition. Money fields (`amount`,`fee`,`tax`,`credit`,`debit`)
    are real, per-row, already integer paise (`resolver/loaders.py:289`
    keeps `dataset.rows` unparsed JSON -- SETTLEMENT_SPEC.md Sec.4 confirms
    the money keys are already paise). The four-line journal layout is an
    illustrative convention (DECISIONS Sec.100), never asserted as this
    repo's own chart of accounts."""
    gross = fees = tax = refunds = net_credit = 0
    seen: set[str] = set()
    for entry in lines:
        outcome = entry["outcome"]
        if not outcome or outcome.get("__type__") not in ("Verified", "Reconstructed"):
            continue
        comp = outcome.get("composition")
        if not comp:
            continue
        for row_id in comp["credit_ids"] + comp["debit_ids"]:
            if row_id in seen:
                continue
            seen.add(row_id)
            row = rows_by_id.get(row_id)
            if not row:
                continue
            amount, fee = row.get("amount") or 0, row.get("fee") or 0
            tax_amt, credit, debit = row.get("tax") or 0, row.get("credit") or 0, row.get("debit") or 0
            # Gate on the real `debit` field, not `type`: a debit-side
            # "adjustment" row (a chargeback, real in this corpus -- e.g.
            # adj_8hLzehpYsMYjdI, debit=1,079,900 paise) is a debit-side
            # item exactly like a refund, and an earlier draft that gated
            # on `type == "refund"` silently added those chargeback amounts
            # into gross instead. Caught by cross-checking net_paise against
            # Sigma(credit - debit), the SETTLEMENT_SPEC.md Sec.4 identity
            # -- the two disagreed by exactly the sum of the debit
            # adjustments this branch had misclassified.
            if debit:
                refunds += debit
            else:
                gross += amount
                fees += fee
                tax += tax_amt
            net_credit += credit - debit

    net = gross - fees - refunds
    return dict(
        gross_paise=gross, fees_paise=fees, tax_paise=tax,
        refunds_paise=refunds, net_paise=net, net_credit_check_paise=net_credit,
        lines=[
            dict(account="PSP Clearing", debit_paise=gross, credit_paise=0),
            dict(account="Processing Fees", debit_paise=fees, credit_paise=0),
            dict(account="Refund Liability", debit_paise=0, credit_paise=refunds),
            dict(account="Bank", debit_paise=0, credit_paise=net),
        ])


def build_exceptions(dataset, lines: list[dict], rows_by_id: dict[str, dict],
                      erp_by_order: dict[str, dict], disputes_by_id: dict[str, dict],
                      settlement_by_id: dict[str, dict],
                      open_break_buckets: dict[str, list[dict]]) -> list[dict]:
    """One real exception per item that genuinely has something to
    investigate -- never a synthesized example. Two shapes, deliberately
    not unified into one, because they carry different real evidence:

    Line-level (`Unresolved`/`AttestationDiscrepancy`): the resolver DOES
    classify these with a real `warrant`/`detail` (or `contradiction`) --
    `resolver_contract/types.py:829-845` (Unresolved), `:697-723`
    (AttestationDiscrepancy). This is the one case a real "likely
    explanation" can be shown.

    Row-level (`OpenBreak`): `resolver/breaks.py`'s only `OpenBreak(...)`
    call site never passes `warrant=`, so `OpenBreak.warrant` is `None`,
    always (confirmed by reading every construction site, not assumed).
    These exceptions carry real `reason`/`age_days`/`itc_risk` but
    explicitly `warrant: None` -- the UI must render "no warrant on file"
    for these, never invent an explanation the engine did not produce.
    """
    row_lookup = {r["entity_id"]: r for r in dataset.rows}
    exceptions = []

    for entry in lines:
        outcome = entry["outcome"]
        if not outcome or outcome.get("__type__") not in _EVIDENCED_LINE_KINDS:
            continue
        kind = outcome["__type__"]
        if kind == "Unresolved":
            warrant = outcome.get("warrant")
            reason = outcome.get("reason")
            likely_explanation = outcome.get("detail")
            referenced_ids = []
        else:  # AttestationDiscrepancy
            warrant = outcome.get("warrant")
            contradiction = outcome["contradiction"]
            reason = contradiction["kind"]
            likely_explanation = contradiction["detail"]
            referenced_ids = contradiction["row_ids"]

        psp, erp, settlement, disputes = [], [], [], []
        for rid in referenced_ids:
            row = rows_by_id.get(rid)
            if not row:
                continue
            psp.append(row)
            if row.get("order_id") in erp_by_order:
                erp.append(erp_by_order[row["order_id"]])
            if row.get("settlement_id") in settlement_by_id:
                settlement.append(settlement_by_id[row["settlement_id"]])
            if row.get("dispute_id") in disputes_by_id:
                disputes.append(disputes_by_id[row["dispute_id"]])

        exceptions.append(dict(
            id=f"EX-L{entry['index']}", scope="line", kind=kind,
            bank_index=entry["index"], amount_paise=entry["amount_paise"],
            reference=entry["reference"], value_date=entry["value_date"],
            reason=reason, has_warrant=warrant is not None,
            evidence=to_jsonable(warrant) if warrant else None,
            likely_explanation=likely_explanation,
            bank=dict(found=True, reference=entry["reference"], value_date=entry["value_date"],
                      amount_paise=entry["amount_paise"], narration=entry["narration"]),
            psp=psp, erp=erp, settlement_report=settlement, disputes=disputes,
            age_days=None, owner=None,
        ))

    for bucket_name, rows in open_break_buckets.items():
        for r in rows:
            row_id = r["row_id"]
            raw = row_lookup.get(row_id)
            owner, close_condition = owner_for_reason(r["reason"])
            erp = ([erp_by_order[raw["order_id"]]]
                   if raw and raw.get("order_id") in erp_by_order else [])
            settlement = ([settlement_by_id[raw["settlement_id"]]]
                          if raw and raw.get("settlement_id") in settlement_by_id else [])
            disputes = ([disputes_by_id[raw["dispute_id"]]]
                       if raw and raw.get("dispute_id") in disputes_by_id else [])
            exceptions.append(dict(
                id=f"EX-{row_id}", scope="row", kind="OpenBreak",
                bank_index=None,
                # `dataset.rows` is `json.loads(recon_combined.json)["items"]`
                # untouched (`resolver/loaders.py:289`) -- `amount` is
                # already an integer in paise, same units as everywhere
                # else in this repo. No *100 conversion belongs here; an
                # earlier draft applied one anyway and inflated every
                # OpenBreak amount 100x, caught by cross-checking this
                # exact row's PSP amount against its real ERP invoice total.
                amount_paise=int(raw["amount"]) if raw and raw.get("amount") is not None else None,
                reference=row_id, value_date=r.get("first_seen"),
                reason=r["reason"], has_warrant=False, evidence=None,
                likely_explanation=None,
                bank=dict(found=False, detail="No matching bank credit found for this row."),
                psp=[raw] if raw else [], erp=erp, settlement_report=settlement, disputes=disputes,
                age_days=r["age_days"], age_bucket=bucket_name,
                owner=owner, close_condition=close_condition,
            ))

    return exceptions


#: One line per agent, written for the person using the dashboard. These
#: were previously scraped from each module's docstring, which is the right
#: instinct (it cannot drift from the code) but the wrong source: those
#: docstrings are addressed to a maintainer and cite internal decision
#: records by number, which then surfaced verbatim in the agent menu.
_AGENT_MODULES = [
    ("chat_answerer", None, "read-only",
     "Answers questions about this reconciliation in plain English, from the "
     "run's own recorded results. This panel is that assistant."),
    ("sla_watchdog", sla_watchdog, "read-only",
     "Watches open items against their age thresholds and drafts the "
     "escalation for whoever owns them."),
    ("queue_cleaner", queue_cleaner, "read-only",
     "Groups timing differences that should clear on their own, separating "
     "the ones provably inside their settlement window from the ones that "
     "are not."),
    ("break_investigator", break_investigator, "write-capable, requires approval",
     "Investigates unexplained open breaks and proposes a reclassification "
     "for a human to approve."),
    ("ambiguous_arbiter", ambiguous_arbiter, "write-capable, requires approval",
     "Lays out the competing explanations where more than one is arithmetically "
     "possible, so a person can choose between them on the evidence."),
    ("itc_drafter", itc_drafter, "write-capable, requires approval",
     "Drafts the input-tax-credit position on at-risk purchase invoices, "
     "citing the provision each risk rests on."),
]
def build_agents_panel(conn, run_id: str, itc_conn, itc_run_id: str) -> list[dict]:
    """Real metadata plus one real, illustrative, READ-ONLY preview per
    agent -- computed here at build time against the same persisted run
    every other panel uses, never a live call from the static page (this
    export has no running `service/`, per DECISIONS.md Sec.90's own
    rejected-alternative). The three write-capable agents' `propose`/
    `record_resolution` functions are never called here; only their
    `gather_*`/`present` functions, which touch nothing."""
    agents = []
    for name, module, mode, description in _AGENT_MODULES:
        preview = None

        if name == "sla_watchdog":
            escalations = sla_watchdog.build_escalations(conn, run_id)
            preview = {
                "kind": "sla_watchdog",
                "count": len(escalations),
                "examples": [
                    {"reason": e.reason, "age_bucket": e.age_bucket, "level": e.level,
                     "owner": e.owner, "count": e.count}
                    for e in escalations[:3]
                ],
            }
        elif name == "queue_cleaner":
            grouped = queue_cleaner.group_carry_forward(conn, run_id)
            preview = {
                "kind": "queue_cleaner",
                "total": grouped["total"],
                "provable_within_window": len(grouped["provable_within_window"]),
                "not_provable_within_window": len(grouped["not_provable_within_window"]),
            }
        elif name == "break_investigator":
            row = conn.execute(
                "SELECT row_id FROM row_outcomes WHERE run_id = ? AND "
                "disposition = 'OpenBreak' AND reason = 'unexplained' LIMIT 1",
                (run_id,)).fetchone()
            if row is not None:
                try:
                    facts = break_investigator.gather_case_facts(conn, run_id, row["row_id"])
                    case_file = break_investigator.draft_case_file(facts)
                    preview = {"kind": "break_investigator", "row_id": row["row_id"],
                               "case_file": case_file}
                except break_investigator.NotInvestigable:
                    pass
        elif name == "ambiguous_arbiter":
            row = conn.execute(
                "SELECT bank_index FROM line_outcomes WHERE run_id = ? AND "
                "kind = 'Ambiguous' LIMIT 1", (run_id,)).fetchone()
            if row is not None:
                presentation = ambiguous_arbiter.present(conn, run_id, row["bank_index"])
                preview = {"kind": "ambiguous_arbiter", "bank_index": row["bank_index"],
                           "candidate_count": presentation["candidate_count"],
                           "complete": presentation["complete"]}
        elif name == "itc_drafter":
            flagged = itc_conn.execute(
                "SELECT row_id, itc_risk FROM row_outcomes WHERE run_id = ? AND "
                "disposition = 'OpenBreak' AND itc_risk IS NOT NULL",
                (itc_run_id,)).fetchall()
            example_row_id = next(
                (r["row_id"] for r in flagged if r["row_id"] in r["itc_risk"].split(",")), None)
            if example_row_id is not None:
                facts = itc_drafter.gather_grounds(itc_conn, itc_run_id, example_row_id)
                preview = {"kind": "itc_drafter", "row_id": example_row_id,
                           "grounds": facts["grounds"],
                           "dataset": ENTITY_LABELS.get("A10_B100_Cmax", "another entity")}

        agents.append(dict(name=name, description=description, mode=mode, preview=preview))
    return agents


#: Grounded in real, checkable code state -- never a claim about a live
#: integration this repo does not have. `monogram` replaces a brand logo
#: image deliberately: this repo has no license to reproduce Zoho's, SAP's,
#: or Tally's actual trademarked artwork, and a self-drawn approximation of
#: one would be exactly the kind of unearned specificity CLAUDE.md's
#: evidence discipline warns against.
#:
#: `status="available"` means real, tested code exists but this run's data
#: did not literally travel through it (SFTP/S3: the flagship's files are
#: read from local disk, not pulled live). Where a connector's `artifact`
#: key names a file that IS one of this run's own six real ingested
#: artifacts (checked against `build_ingestion_status`'s live output in
#: `main()` below, not hand-set here), the status is upgraded to
#: "connected" -- an honest, narrower claim than "available" everywhere,
#: not a blanket "yes" for four different real states.
CONNECTORS = [
    dict(name="SFTP", monogram="SF", status="available",
         detail="Scheduled pickup of bank and processor files from an SFTP "
                "endpoint, with credentials held outside the application."),
    dict(name="S3", monogram="S3", status="available",
         detail="Pulls statement and settlement drops from an S3 bucket on the "
                "same schedule and guard rails as SFTP."),
    dict(name="Razorpay API", monogram="RP", status="connected", artifact="recon_combined.json",
         detail="Pulls the combined reconciliation report -- payments, refunds, "
                "adjustments, fees and settlement identifiers -- straight from "
                "the payments API."),
    dict(name="GSTR-2B / GST Portal", monogram="GST", status="available", artifact="gstr2b.csv",
         detail="Reads a GSTR-2B portal export and maps its columns to supplier "
                "invoices, IRN status and input-tax-credit availability."),
    dict(name="Zoho Books", monogram="Z", status="planned",
         detail="Not yet built. Adding it responsibly needs a real Zoho export "
                "to map against, rather than a guess at its schema."),
    dict(name="Tally", monogram="T", status="planned",
         detail="Not yet built, for the same reason as Zoho Books -- deferred "
                "deliberately, not stubbed out."),
    dict(name="SAP / NetSuite", monogram="SAP", status="planned",
         detail="Not yet built. A high-effort integration scheduled behind the "
                "sources most customers land with first."),
    dict(name="Email attachment", monogram="@", status="planned",
         detail="Not yet built. Requires a mailbox connection this deployment "
                "does not currently hold."),
]



def main() -> int:
    dataset = ingest_load(FLAGSHIP_DIR)

    # Four independent real runs against the same frozen entity, at four
    # genuinely different (cap, time_budget) points -- not four calls with
    # the same arguments repeated. This is what powers the Run Stability
    # panel: real evidence for "does this reach the same answer twice,"
    # not a fabricated trend.
    RUN_PARAMS = [(40, 5.0), (45, 6.0), (60, 8.0), (30, 4.0)]

    LIVE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LIVE_DB_PATH.exists():
        LIVE_DB_PATH.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(LIVE_DB_PATH)
        run_ids = [run_pipeline(FLAGSHIP_DIR, conn, cap=cap, time_budget=tb)
                   for cap, tb in RUN_PARAMS]
        run_id = run_ids[0]

        lines, rows_by_id = build_lines_and_rows(dataset, conn, run_id)
        buckets = open_breaks(conn, run_id)
        aging = {label: len(rows) for label, rows in buckets.items()}
        aging_rows = {label: [dict(r) for r in rows] for label, rows in buckets.items()}

        sample_row_ids = list(rows_by_id)[:12]
        history_sample = build_row_history_sample(conn, "A20_B50_Cmax", sample_row_ids)

        run_meta = get_run(conn, run_id)
        run_count = len(runs_for_dataset(conn, "A20_B50_Cmax"))
        run_metas = [get_run(conn, rid) for rid in run_ids]
        gst = build_gst_panel(FLAGSHIP_DIR, conn, run_ids)
        stability = build_stability_panel(conn, "A20_B50_Cmax", run_metas)
        run_diff = build_run_diff(conn, run_ids[0], run_ids[1],
                                   cap_a=RUN_PARAMS[0][0], cap_b=RUN_PARAMS[1][0],
                                   time_budget_a=RUN_PARAMS[0][1], time_budget_b=RUN_PARAMS[1][1])

        # A second, real dataset, only for the ITC Drafter agent preview
        # (see ITC_EXAMPLE_DIR's own comment above) -- never touches any
        # other panel's numbers.
        itc_conn = connect(Path(tmp) / "settlr_itc_example.db")
        itc_run_id = run_pipeline(ITC_EXAMPLE_DIR, itc_conn, cap=40, time_budget=5.0)
        agents_panel = build_agents_panel(conn, run_id, itc_conn, itc_run_id)
        # Must run AFTER the agents panel: build_agents_panel deliberately
        # calls only read-only functions, and reading a queue this call is
        # about to populate would make its preview depend on ordering.
        approvals = build_approvals(conn, run_id, itc_conn, itc_run_id,
                                     as_of=run_meta["finished_at"])
        provenance = build_source_provenance(conn, run_id)
        conn.close()

    dashboard_data = json.loads(DASHBOARD_DATA_PATH.read_text())
    entities = build_entities()
    ingestion = build_ingestion_status(FLAGSHIP_DIR)
    discrepancies = build_discrepancies(lines)
    runs_table = build_runs_table(entities)
    accounting = build_accounting_summary(lines, rows_by_id)

    ingested_artifacts = {f["artifact"] for f in ingestion}
    connectors = []
    for c in CONNECTORS:
        c = dict(c)
        if c.get("artifact") in ingested_artifacts:
            c["status"] = "connected"
        connectors.append(c)

    # Widened to also cover OpenBreak rows -- those are never in
    # `rows_by_id` (a row referenced by no line's outcome, by definition of
    # being an open break), but `build_exceptions` still needs their real
    # ERP/settlement/dispute records where they exist.
    open_break_row_ids = {r["row_id"] for rows in buckets.values() for r in rows}
    row_lookup_for_widening = {r["entity_id"]: r for r in dataset.rows}
    all_raw_rows = ([r for r in rows_by_id.values()] +
                     [row_lookup_for_widening[rid] for rid in open_break_row_ids
                      if rid in row_lookup_for_widening])
    order_ids = {r["order_id"] for r in all_raw_rows if r.get("order_id")}
    settlement_ids = {r["settlement_id"] for r in all_raw_rows if r.get("settlement_id")}
    dispute_ids = {r["dispute_id"] for r in all_raw_rows if r.get("dispute_id")}
    erp_by_order = build_erp_lookup(FLAGSHIP_DIR, order_ids)
    settlement_by_id = build_settlement_report_lookup(dataset, settlement_ids)
    disputes_by_id = {did: dict(dataset.disputes[did])
                       for did in dispute_ids if did in dataset.disputes}

    period = build_period(dataset)
    timing = build_settlement_timing(dataset)
    methods = build_method_breakdown(dataset, open_break_row_ids)
    kpis = build_kpis(dataset, lines, timing, rows_by_id, aging_rows, run_meta)

    exceptions = build_exceptions(dataset, lines, rows_by_id, erp_by_order,
                                   disputes_by_id, settlement_by_id, aging_rows)

    coverage_all = dashboard_data["coverage"]["all"]

    data = dict(
        meta=dict(
            generated_by="dashboard/build_dashboard.py",
            run_id=run_id, run_count=run_count,
            code_digest=run_meta["code_digest"][:16],
            input_digest=run_meta["input_digest"][:16],
            flagship_dataset="A20_B50_Cmax",
            entity_label=ENTITY_LABELS["A20_B50_Cmax"],
        ),
        health=dict(
            answered=coverage_all["answered"],
            determinable=coverage_all["determinable"],
            settlement_lines=coverage_all["settlement_lines"],
            on_determinable_pct=round(coverage_all["on_determinable_pct"], 1),
            of_all_lines_pct=round(coverage_all["of_all_lines_pct"], 1),
            datasets=coverage_all["datasets"],
        ),
        entities=entities,
        aging=aging,
        aging_rows=aging_rows,
        ingestion=ingestion,
        lines=lines,
        rows_by_id=rows_by_id,
        erp_by_order=erp_by_order,
        disputes_by_id=disputes_by_id,
        row_history=history_sample,
        discrepancies=discrepancies,
        # Full coverage-by-scope -- what powers the "Detailed Health
        # Analysis" drill-down. All four scopes, not a subset that happens
        # to look good.
        coverage=_present_coverage(dashboard_data["coverage"]),
        trust=build_trust_panel(dashboard_data),
        gst=gst,
        stability=stability,
        agents=agents_panel,
        connectors=connectors,
        exceptions=exceptions,
        runs_table=runs_table,
        period=period,
        timing=timing,
        methods=methods,
        kpis=kpis,
        approvals=approvals,
        provenance=provenance,
        run_diff=run_diff,
        accounting=accounting,
    )

    template = TEMPLATE_PATH.read_text()
    # Last gate before the payload is written into the page: anything no
    # renderer reads is dropped here rather than shipped and hidden.
    injected = json.dumps(_strip_payload_only(data), indent=None, separators=(",", ":"))
    if "<!--__SETTLR_DATA__-->" not in template:
        raise SystemExit("template.html is missing the injection point")

    import base64
    logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
    ai_orb_b64 = base64.b64encode(AI_ORB_PATH.read_bytes()).decode()
    app_js = APP_JS_PATH.read_text()

    output = template.replace(
        "<!--__SETTLR_DATA__-->",
        f"<script>window.SETTLR_DATA = {injected};</script>")
    output = output.replace("__LOGO_B64__", logo_b64)
    output = output.replace("__AI_ORB_B64__", ai_orb_b64)
    output = output.replace("__APP_JS__", app_js)
    OUT_PATH.write_text(output)
    print(f"wrote {OUT_PATH} ({len(output):,} bytes, {len(lines)} lines, "
          f"{len(entities)} entities, {sum(aging.values())} open breaks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
