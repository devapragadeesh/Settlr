"""SQLite persistence, layered strictly downstream of `resolver/` and
`resolver_contract/`. `tests/test_layer_isolation.py` enforces that
`resolver/` never imports this package.

`store/codec.py` -- lossless dataclass<->JSON for the outcome vocabulary.
`store/db.py` -- connection + schema (plain SQL, no ORM).
`store/writer.py` -- `ResolverOutput` -> rows, one transaction, idempotent on
`run_id`.
`store/queries.py` -- the read side, including `row_history`, which answers
the audit-trail question `investigation/CONTROLS_MAPPING.md` Sec.3(b) names
as absent: whether and how a row's outcome changed across runs.
"""
