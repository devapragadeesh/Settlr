"""The service layer: pull -> ingest -> resolve -> persist, a scheduler, and
a read-only API over `store/queries.py`. Layered strictly downstream of
`resolver/`, `ingest/`, `transport/` and `store/` --
`tests/test_layer_isolation.py` covers this package too.

Depends on `fastapi`/`uvicorn` (`requirements-service.txt`, not
`requirements.txt`) -- a cold clone running only `pytest`/`run_all.py` never
needs this package or its dependencies.
"""
