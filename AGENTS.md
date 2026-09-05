# AGENTS.md

This file orients a coding agent to this repository. It is a map and a set
of boundaries, not a tutorial — see [`README.md`](README.md) for what the
project is and why, [`CLAUDE.md`](CLAUDE.md) for Claude-Code-specific
workflow notes, and `DECISIONS.md` for the append-only record of every
non-trivial call made in this repo and what was rejected instead.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-service.txt
pytest tests engine/tests corpus/tests resolver/tests -q   # ~30s, the fast suite
```

No API keys or external services are required to run the tests or the
resolver. `agents/` (Claude-narrated helpers) degrade to a deterministic
fallback with no key configured — see `agents/base.py`.

## Layout and what an agent may touch

```
resolver_contract/   outcome vocabulary. Interface only, no algorithm.
resolver/             the live solver. Frozen contract; new logic goes here.
engine/, matching/    FROZEN. Reference-only. Never edit; DECISIONS.md
                       explains why (they are the demoted baseline this
                       project's whole argument is measured against).
corpus/                the benchmark: generator, datasets, oracle, leakage audit.
ingest/ transport/ store/ service/   ingestion -> persistence -> API layer.
                       Must never import resolver/resolver_contract/matching/
                       engine directly outside of store/queries.py's own use
                       of resolver_contract -- enforced by
                       tests/test_layer_isolation.py.
agents/                Claude-narrated helpers. Never assign or classify a
                       row's outcome on their own authority; only propose,
                       gated behind an approval table a human must clear.
dashboard/             the generated product UI (dashboard/index.html is
                       build output, edit dashboard/build_dashboard.py and
                       dashboard/web/{template.html,app.js} instead).
investigation/         dated findings, predictions committed before a fix,
                       before/after measurements. Read before assuming a
                       defect is unknown or already fixed.
docs/                  DECISIONS.md, CLAIMS.md, SCORECARD.md, CHECKPOINT.md,
                       TEST_PLAN.md. SCORECARD/CLAIMS are GENERATED into this
                       directory (corpus/scorecard.py, corpus/claims_ledger.py)
                       -- never hand-edit them.
assets/                brand and UI source images. dashboard/build_dashboard.py
                       inlines assets/aibutton.png at build time.
```

**One-way dependency, enforced by tests, not convention:** `resolver/` never
reads `eval/`; `eval/` is the only package permitted to read
`engine/ground_truth/`; `matching/` may never appear in that allowlist.
Breaking this is the single easiest way to invalidate every number this repo
publishes — see `tests/test_isolation.py` and `engine/tests/test_no_leakage.py`.

## Before changing code

1. Read `DECISIONS.md`'s most recent ~5 entries for the numbering convention
   and this repo's evidence discipline (every claim ships with what was
   rejected and why).
2. Check whether the file you're about to touch is frozen (see above). A
   frozen path needs a new file in a new directory, not an edit in place.
3. If you're changing `dashboard/`, run `node --check dashboard/web/app.js`
   before rebuilding — the build step does not catch JS syntax errors on
   its own.

## Testing

```bash
pytest tests engine/tests corpus/tests resolver/tests ingest/tests transport/tests service/tests store/tests agents/tests -q
```

~1300+ tests, ~15 minutes cold. CI (`.github/workflows/ci.yml`) runs this
split across four parallel jobs plus the leakage audit; badge above the fold
in `README.md`. `scale/data_*` (throughput fixtures, ~30 min to regenerate,
`python3 scale/generate_scale.py`) is gitignored by design — the CI-facing
tests degrade their expected counts when it's absent rather than failing on
a fresh checkout; see `ingest/tests/test_conformance.py` and
`tests/adversarial/test_malformed_bank.py`.

## Scoped permissions

- **Safe to run freely:** any `pytest` target, `dashboard/build_dashboard.py`,
  read-only scripts under `corpus/` and `eval/`.
- **Never edit:** anything under `engine/data/`, `engine/ground_truth/`,
  `engine/simulator.py`, `engine/generator.py`, `matching/` — frozen, see
  `CLAUDE.md`.
- **Requires a recorded decision first:** any change to `resolver_contract/`
  (the outcome vocabulary every other layer depends on), any new
  write-capable path in `agents/` (they propose, never assign — a new write
  path is a new claim about that boundary and needs its own `DECISIONS.md`
  entry before code).
