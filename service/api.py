"""Read-only HTTP over `store/queries.py`. No write endpoint exists --
every mutation happens through `service/pipeline.py::run_pipeline`, run
out-of-band by `service/poller.py`'s scheduler, never through a request.

Every response is built through `store/codec.py::to_jsonable` rather than
FastAPI's own `jsonable_encoder`, so there is exactly one place in the repo
that knows how to turn an `Evidence`/`Warrant`/`Composition` into JSON, not
two competing implementations that could drift.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from store.codec import to_jsonable
from store.db import connect
from store.queries import (break_lifecycle, get_run, line_outcome,
                            open_breaks, row_history, row_outcome,
                            runs_for_dataset)


def create_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="Settlement Truth Engine -- read-only store API")

    def get_conn() -> sqlite3.Connection:
        return connect(db_path)

    @app.get("/runs")
    def list_runs(dataset: str):
        conn = get_conn()
        try:
            return runs_for_dataset(conn, dataset)
        finally:
            conn.close()

    @app.get("/runs/{run_id}")
    def run_detail(run_id: str):
        conn = get_conn()
        try:
            run = get_run(conn, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="run not found")
            return run
        finally:
            conn.close()

    @app.get("/runs/{run_id}/lines/{bank_index}")
    def line_detail(run_id: str, bank_index: int):
        conn = get_conn()
        try:
            outcome = line_outcome(conn, run_id, bank_index)
            if outcome is None:
                raise HTTPException(status_code=404, detail="line outcome not found")
            return JSONResponse(content=to_jsonable(outcome))
        finally:
            conn.close()

    @app.get("/runs/{run_id}/rows/{row_id}")
    def row_detail(run_id: str, row_id: str):
        conn = get_conn()
        try:
            outcome = row_outcome(conn, run_id, row_id)
            if outcome is None:
                raise HTTPException(status_code=404, detail="row outcome not found")
            return JSONResponse(content=to_jsonable(outcome))
        finally:
            conn.close()

    @app.get("/runs/{run_id}/breaks")
    def breaks(run_id: str):
        conn = get_conn()
        try:
            return open_breaks(conn, run_id)
        finally:
            conn.close()

    @app.get("/rows/{dataset}/{row_id}/history")
    def history(dataset: str, row_id: str):
        conn = get_conn()
        try:
            return row_history(conn, dataset, row_id)
        finally:
            conn.close()

    @app.get("/breaks/{row_id}/lifecycle")
    def lifecycle(row_id: str):
        conn = get_conn()
        try:
            record = break_lifecycle(conn, row_id)
            if record is None:
                raise HTTPException(status_code=404, detail="no break history for this row")
            return record
        finally:
            conn.close()

    return app
