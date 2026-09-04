"""The read-only API, exercised through FastAPI's in-process `TestClient` --
an ASGI transport, not a real socket, so this stays offline like every other
test in the new layers.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from service.api import create_app
from service.pipeline import run_pipeline
from store.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "corpus" / "datasets" / "A10_B100_Cmax"


@pytest.fixture(scope="module")
def populated_db(tmp_path_factory) -> Path:
    db_path = tmp_path_factory.mktemp("api") / "test.db"
    conn = connect(db_path)
    run_pipeline(DATASET_DIR, conn, cap=40, time_budget=3.0)
    conn.close()
    return db_path


@pytest.fixture()
def client(populated_db: Path) -> TestClient:
    return TestClient(create_app(populated_db))


def test_list_runs_for_dataset(client: TestClient) -> None:
    response = client.get("/runs", params={"dataset": "A10_B100_Cmax"})
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["dataset"] == "A10_B100_Cmax"


def test_run_detail_and_404(client: TestClient) -> None:
    runs = client.get("/runs", params={"dataset": "A10_B100_Cmax"}).json()
    run_id = runs[0]["run_id"]

    response = client.get(f"/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["run_id"] == run_id

    missing = client.get("/runs/nonexistent")
    assert missing.status_code == 404


def test_line_detail_returns_a_jsonable_outcome(client: TestClient) -> None:
    runs = client.get("/runs", params={"dataset": "A10_B100_Cmax"}).json()
    run_id = runs[0]["run_id"]

    response = client.get(f"/runs/{run_id}/lines/0")
    assert response.status_code == 200
    body = response.json()
    assert "__type__" in body
    assert body["bank_index"] == 0


def test_breaks_endpoint_returns_bucketed_rows(client: TestClient) -> None:
    runs = client.get("/runs", params={"dataset": "A10_B100_Cmax"}).json()
    run_id = runs[0]["run_id"]

    response = client.get(f"/runs/{run_id}/breaks")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"0-30", "31-60", "61-90", "90+"}


def test_row_history_endpoint(client: TestClient) -> None:
    response = client.get("/rows/A10_B100_Cmax/some_row/history")
    assert response.status_code == 200
    assert response.json() == []  # a row_id this dataset never used


def test_lifecycle_404_for_a_row_with_no_break_history(client: TestClient) -> None:
    response = client.get("/breaks/nonexistent_row/lifecycle")
    assert response.status_code == 404


def test_lines_summary_matches_line_count_and_is_scalar_only(client: TestClient) -> None:
    runs = client.get("/runs", params={"dataset": "A10_B100_Cmax"}).json()
    run_id = runs[0]["run_id"]

    response = client.get(f"/runs/{run_id}/lines")
    assert response.status_code == 200
    lines = response.json()
    assert len(lines) == 20  # A10_B100_Cmax's own bank-line count
    assert {"bank_index", "kind", "reason", "rival_closure_count",
            "candidate_count", "detail"} == set(lines[0])
    # No `outcome_json`/nested warrant here -- that is what /lines/{bank_index} is for.
    assert "outcome_json" not in lines[0]


def test_sources_endpoint_lists_every_ingested_artifact(client: TestClient) -> None:
    runs = client.get("/runs", params={"dataset": "A10_B100_Cmax"}).json()
    run_id = runs[0]["run_id"]

    response = client.get(f"/runs/{run_id}/sources")
    assert response.status_code == 200
    sources = response.json()
    artifact_names = {s["artifact_path"] for s in sources}
    assert artifact_names == {"bank_statement.csv", "settlement_report.csv",
                              "erp_orders.csv", "gstr2b.csv", "disputes.json",
                              "recon_combined.json"}


def test_transaction_flow_ui_serves_the_real_html_file(client: TestClient) -> None:
    response = client.get("/ui/transaction-flow")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Transaction Flow" in response.text
    assert "/runs/${RUN_ID}/lines" in response.text  # same-origin fetch, no CORS needed
