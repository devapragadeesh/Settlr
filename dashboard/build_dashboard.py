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
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest import load as ingest_load  # noqa: E402
from resolver_contract.types import SourceSystem  # noqa: E402
from service.pipeline import run_pipeline  # noqa: E402
from store.codec import to_jsonable  # noqa: E402
from store.db import connect  # noqa: E402
from store.queries import (get_run, line_outcome, open_breaks,  # noqa: E402
                            row_history, runs_for_dataset)

FLAGSHIP_DIR = ROOT / "corpus" / "datasets" / "A20_B50_Cmax"
TEMPLATE_PATH = ROOT / "dashboard" / "web" / "template.html"
APP_JS_PATH = ROOT / "dashboard" / "web" / "app.js"
LOGO_PATH = ROOT / "dashboard" / "web" / "logo_lockup.png"
OUT_PATH = ROOT / "dashboard" / "index.html"
DASHBOARD_DATA_PATH = ROOT / "dashboard" / "data.json"
ORACLE_RESULTS_PATH = ROOT / "corpus" / "oracle_results.json"

#: filename -> (SourceSystem, human label). The six-artifact contract every
#: dataset directory in this repo carries.
ARTIFACT_SOURCES = {
    "recon_combined.json": (SourceSystem.PSP_LEDGER, "PSP Ledger Feed"),
    "bank_statement.csv": (SourceSystem.BANK, "Bank Statement"),
    "settlement_report.csv": (SourceSystem.PSP_SETTLEMENT_REPORT, "PSP Settlement Report"),
    "erp_orders.csv": (SourceSystem.MERCHANT_ERP, "ERP Order Book"),
    "gstr2b.csv": (SourceSystem.TAX_AUTHORITY, "GSTR-2B (Tax Authority)"),
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


def _friendly_label(axis_point: str) -> str:
    return ENTITY_LABELS.get(axis_point, axis_point.replace("_", " · "))


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
            label=_friendly_label(axis_point),
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
                    dispute_id=raw.get("dispute_id"))

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

    three_systems = dict(naive=_agg("naive"), frozen=_agg("frozen"),
                          resolver=_agg("resolver"),
                          source=dashboard_data.get("three_systems", {}).get("source"))

    commit_ordering = dashboard_data.get("commit_ordering") or {}
    hashes = dashboard_data.get("hashes")

    return dict(
        three_systems=three_systems,
        d15=dashboard_data.get("d15"),
        self_correction=dashboard_data.get("self_correction_record"),
        commit_count=commit_ordering.get("count"),
        first_commit=(commit_ordering.get("first_ten") or [{}])[0],
        hashes_verified=hashes,
    )


def main() -> int:
    dataset = ingest_load(FLAGSHIP_DIR)

    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "settlr_demo.db")
        run_id = run_pipeline(FLAGSHIP_DIR, conn, cap=40, time_budget=5.0)
        run_pipeline(FLAGSHIP_DIR, conn, cap=45, time_budget=6.0)  # a second, real run

        lines, rows_by_id = build_lines_and_rows(dataset, conn, run_id)
        buckets = open_breaks(conn, run_id)
        aging = {label: len(rows) for label, rows in buckets.items()}
        aging_rows = {label: [dict(r) for r in rows] for label, rows in buckets.items()}

        sample_row_ids = list(rows_by_id)[:12]
        history_sample = build_row_history_sample(conn, "A20_B50_Cmax", sample_row_ids)

        run_meta = get_run(conn, run_id)
        run_count = len(runs_for_dataset(conn, "A20_B50_Cmax"))

    dashboard_data = json.loads(DASHBOARD_DATA_PATH.read_text())
    entities = build_entities()
    ingestion = build_ingestion_status(FLAGSHIP_DIR)
    discrepancies = build_discrepancies(lines)

    order_ids = {r["order_id"] for r in rows_by_id.values() if r.get("order_id")}
    erp_by_order = build_erp_lookup(FLAGSHIP_DIR, order_ids)
    disputes_by_id = {did: dict(dataset.disputes[did])
                       for r in rows_by_id.values()
                       if (did := r.get("dispute_id"))}

    coverage_all = dashboard_data["coverage"]["all"]

    data = dict(
        meta=dict(
            generated_by="dashboard/build_dashboard.py",
            run_id=run_id, run_count=run_count,
            code_digest=run_meta["code_digest"][:16],
            input_digest=run_meta["input_digest"][:16],
            flagship_dataset="A20_B50_Cmax",
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
        # Full coverage-by-scope and the complete claims ledger, both already
        # computed by corpus/claims_ledger.py and corpus/coverage.py and
        # passed through dashboard/data.json untouched -- this is what powers
        # the "Detailed Health Analysis" panel. Not curated/filtered here:
        # showing all 25 claims and all 4 scopes is more honest than picking
        # a subset that happens to look good.
        coverage=dashboard_data["coverage"],
        claims=dashboard_data["claims"],
        trust=build_trust_panel(dashboard_data),
    )

    template = TEMPLATE_PATH.read_text()
    injected = json.dumps(data, indent=None, separators=(",", ":"))
    if "<!--__SETTLR_DATA__-->" not in template:
        raise SystemExit("template.html is missing the injection point")

    import base64
    logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
    app_js = APP_JS_PATH.read_text()

    output = template.replace(
        "<!--__SETTLR_DATA__-->",
        f"<script>window.SETTLR_DATA = {injected};</script>")
    output = output.replace("__LOGO_B64__", logo_b64)
    output = output.replace("__APP_JS__", app_js)
    OUT_PATH.write_text(output)
    print(f"wrote {OUT_PATH} ({len(output):,} bytes, {len(lines)} lines, "
          f"{len(entities)} entities, {sum(aging.values())} open breaks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
