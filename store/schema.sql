-- Persistence schema, Track C. Plain SQL, applied by store/db.py's tiny
-- forward-only migrator -- no Alembic, no ORM. Money is INTEGER paise
-- throughout, matching CLAUDE.md's rule everywhere else in this repo.
--
-- Every LineOutcome/RowOutcome is stored TWICE, deliberately: scalar columns
-- for the queries store/queries.py actually needs (kind, reason, aging), and
-- a full JSON blob (via store/codec.py) that reconstructs the exact
-- dataclass instance losslessly. Full third-normal-form tables for Warrant/
-- Evidence/Contradiction/Composition/CandidateSet were considered and
-- rejected -- see DECISIONS.md's entry for this schema for why.

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    resolver TEXT NOT NULL,
    code_digest TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    cap INTEGER NOT NULL,
    time_budget REAL NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    seconds REAL NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    artifact_path TEXT NOT NULL,
    source_system TEXT NOT NULL,
    format TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    fetched_at TEXT,
    transport TEXT,
    PRIMARY KEY (run_id, artifact_path)
);

CREATE TABLE IF NOT EXISTS line_outcomes (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    bank_index INTEGER NOT NULL,
    kind TEXT NOT NULL,
    reason TEXT,
    pool_size INTEGER,
    rival_closure_count INTEGER,
    rival_count_is_lower_bound INTEGER,
    candidate_count INTEGER,
    candidate_complete INTEGER,
    enumeration_cap INTEGER,
    nearest_residual INTEGER,
    detail TEXT,
    outcome_json TEXT NOT NULL,
    PRIMARY KEY (run_id, bank_index)
);

CREATE TABLE IF NOT EXISTS row_outcomes (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    row_id TEXT NOT NULL,
    disposition TEXT NOT NULL,
    reason TEXT NOT NULL,
    age_days INTEGER,
    first_seen TEXT,
    caused_by INTEGER,
    provable_within_window INTEGER,
    itc_risk TEXT,
    outcome_json TEXT NOT NULL,
    PRIMARY KEY (run_id, row_id)
);

-- Populated incrementally by store/writer.py::record_break_history on every
-- write_run call: the one table in this schema that is NOT simply a replay
-- of one run's ResolverOutput. It is what closes the audit-trail gap named
-- in investigation/CONTROLS_MAPPING.md Sec.3(b) -- "no log of an outcome
-- changing from Ambiguous to Verified as new evidence arrived" -- by
-- recording, across runs, when a row's break first appeared and when a later
-- run stopped reporting it as one.
CREATE TABLE IF NOT EXISTS break_history (
    row_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    first_run_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_run_id TEXT NOT NULL,
    closed_at TEXT,
    close_run_id TEXT
);
