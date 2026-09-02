# CONTROLS MAPPING

> **This is not a compliance certification, an audit opinion, or a claim of
> regulatory conformance.** It is an informational mapping written by this
> project's own contributors against their own hiring-artifact submission. No
> external standards body, auditor, or regulator reviewed it, participated in
> it, or endorsed it. SOX, COSO, and standard bank-reconciliation practice are
> used here only as a **vocabulary** for describing what this repo's tests and
> gates actually do — not as a framework this repo claims to satisfy. Read
> every "maps to" below as "this repo artifact does something with the same
> shape as the named control," never as "this repo is SOX-compliant."

Companion to [`README.md`](../README.md)'s "Limitations" section, in the same
register: name what is true, name what is absent, do not pad. Every claim
below cites the file, test, or gate that does the work. Where nothing does the
work, that is stated plainly instead of stretched into an analogy.

---

## 1. Segregation of duties

**Present, and the strongest mapping in this document.**

The repo enforces a one-way dependency: `engine/` generates the ledger *and*
the isolated ground-truth key; `matching/` (the frozen cascade) and
`resolver/` (the contract-driven resolver) must never read that key; only
`eval/` and `corpus/oracle.py` may. This is architecturally identical to
preparer/reviewer separation — the party that produces the transaction record
is barred from also being the party that certifies the answer, and the barrier
is checked mechanically rather than assumed.

Concretely:

- `tests/test_isolation.py` enforces this over `matching/` four ways: source-text scan for `ground_truth`/`GROUND_TRUTH` tokens (`test_no_matching_module_mentions_the_ground_truth`), an AST-level import ban on `eval`/`engine`/`engine.generator`/`engine.simulator` (`test_no_matching_module_imports_eval_or_engine_internals`), a path-scoping check that any `"engine"` path reference is qualified through `"data"` (`test_no_matching_module_opens_a_path_outside_engine_data`), and a check that `eval/metrics.py` is the *only* module anywhere that reads the key (`test_eval_is_the_only_package_that_reads_the_key`). The last test in the file, `test_the_cascade_runs_without_the_key_present`, is the load-bearing one: it makes the ground-truth file physically unreadable (`monkeypatch.setattr(metrics, "GROUND_TRUTH", tmp_path / "absent.json")`) and asserts the cascade still runs and produces matches — proving the solver does not merely avoid *importing* the key, it does not *need* it to function.
- `resolver/tests/test_isolation.py` re-enforces the identical rule over the newer `resolver/` package, independently, by five mechanisms: source-text scan (`test_no_source_mentions_the_answer_key`), AST constant/attribute scan (`test_no_ast_node_reaches_for_the_key`), static import ban naming `corpus.oracle`, `corpus.generator`, `corpus.baseline`, `matching`, `engine.generator`, `engine.simulator` (`test_no_forbidden_import`), a *live* import-graph check that walks every module in `resolver/` and inspects what actually landed in `sys.modules` (`test_the_live_import_graph_is_clean` — catches a lazy import inside a function body that static analysis misses), and a check that only `resolver/loaders.py` performs any file I/O at all (`test_no_resolver_module_opens_a_file_the_loader_did_not_open`) — the loader itself refuses the ground-truth filename by name (`resolver/loaders.py`'s `FORBIDDEN` set, exercised by `test_the_loader_refuses_the_key_by_name`).
- The module docstring of `resolver/tests/test_isolation.py` documents that this file was added *because* the existing `matching/`-scoped and `engine/`-scoped isolation tests do not cover `resolver/`, and that the exact defect class this guards against (D2, an unguarded `elif` reachable only on held-out data) shipped once inside a 268-test suite that passed. It also documents that the test has been deliberately made to fail once, by inserting a real leak and re-running, so the negative-control claim is not merely assumed.

What this is *not*: there is no human "preparer" and "reviewer" role — both
sides of the separation are code, and the boundary is enforced by tests that
must be run, not by a workflow gate that blocks a merge automatically in CI on
every change (no CI config was found wiring these tests as a required check;
they are run via `pytest`, per `CLAUDE.md`'s documented commands).

**maps to:** preparer/reviewer separation (SOX §404 control-environment
concept) — implemented as a mechanically enforced module boundary (AST scan +
live import graph + a key-absent execution test), not as a human-role
workflow.

---

## 2. Exception aging / break management

**Present as a data structure and a real classification; absent as a live
SLA-tracked process.**

`resolver_contract/types.py`'s `OpenBreak` dataclass (lines ~892–944) is the
artifact: it asserts nothing (`may_consume` — line ~955 — only ever returns
`True` for `Verified`, never for `OpenBreak`, so a break never removes rows
from a pool), and it carries:

- `reason: BreakReason` — a closed six-value enum (`MISSING_SOURCE`,
  `TIMING_DIFFERENCE`, `MAPPING_ISSUE`, `UNEXPECTED_CHANGE`, `TRUE_ERROR`,
  `UPSTREAM_UNRESOLVED`) plus a seventh, `UNEXPLAINED`, kept deliberately
  un-eliminable (the docstring: "a REAL category that must never be
  eliminated by widening the others — that is precisely how ROLLED_FORWARD
  happened").
- `BREAK_ROUTING: dict[BreakReason, tuple[str, str]]` — an (owner,
  close-condition) pair per reason, e.g. `TRUE_ERROR → ("finance", "the
  correcting entry posts")`, `UNEXPECTED_CHANGE → ("disputes ops", "the hold
  or reversal resolves")`. This is genuine owner routing, not decoration —
  `UPSTREAM_UNRESOLVED` requires a `caused_by` bank-line index or the
  dataclass's `__post_init__` raises `ContractViolation`.
- `age_days` and `first_seen`, and an `AGE_BUCKETS` tuple defining the
  standard four buckets (`0-30`, `31-60`, `61-90`, `90+`) via `age_bucket()`.

The real numbers, from `investigation/DERIVED_BRANCH_AUDIT.md` and
`CLAIMS.md`: **4,308 rows are `OpenBreak`** across all 30 datasets, of which
**1,582 are clustered under 54 distinct causing bank lines** (via
`UPSTREAM_UNRESOLVED`/`caused_by`), and **1,472 fall into `UNEXPLAINED`** — a
third of the queue is honestly reported as unclassifiable rather than folded
into a neighboring reason to look tidier. `ProvenUnmatched` (701 rows) is kept
structurally distinct and is never summed with `OpenBreak` in any report
(`DECISIONS.md` §40) — one type asserts a fact, the other does not, and
conflating them is exactly the failure this split was built to fix (the old
`CorrectlyUnmatched` outcome scored 45.7% accurate while every report said "0
wrong answers").

Where the mapping stops: `age_days` is computed once, per generated dataset,
against a **fixed horizon** — `max(line.value_date for line in dataset.bank)`
in `resolver/breaks.py`'s `_age()` (around line 119) — not against wall-clock
time in a running system. There is no re-scoring loop, no SLA breach alert, no
escalation trigger, and no evidence anywhere in the repo of a break's status
changing after it is first classified. "Aged" here means "how old this item
was *at the moment the corpus was generated*," a static snapshot bucketed at
report time, not a live aging clock a production reconciliation desk would
run.

**maps to:** break classification, owner routing, and aging-bucket structure
(GL reconciliation exception-management concept) — implemented as a one-shot
static classification with real owner/reason/bucket fields, not a live,
time-advancing SLA process.

---

## 3. Audit trail

**Two genuinely different things live under this name here, and they must not
be conflated.**

**(a) Audit trail for the benchmark's own integrity — strong.** Every frozen
dataset carries a SHA-256 manifest (`engine/DATASET_HASHES.txt`,
`holdout/DATASET_HASHES.txt`, `scale/DATASET_HASHES.txt`, and one per corpus
axis point under `corpus/datasets/*/DATASET_HASHES.txt`,
`corpus/datasets_v2/*/DATASET_HASHES.txt`, and
`corpus/datasets_bankside/*/DATASET_HASHES.txt` — 33 manifest files found in
total), verifiable with the `shasum -a 256 -c` command `CLAUDE.md` documents.
`tests/test_holdout_freeze.py` hashes nine frozen paths around a live
generation run and asserts equality, so the frozen dataset cannot silently
drift. README's "Ordering is the evidence" section (lines 411–429) documents a
specific, `git log`-verifiable commit order — resolver contract before any
benchmark data existed, seeds before datasets, datasets never reselected,
baseline prediction committed before the baseline was run once — which is a
real, checkable claim about *when* artifacts were produced relative to each
other, not an assertion taken on faith. `CLAIMS.md` itself is a generated
ledger (`corpus/claims_ledger.py`) tying every quantitative claim in the repo
to the exact command that reproduces it.

**(b) Audit trail for an individual resolver decision over time — absent.**
There is no evidence anywhere in the repo of who (or what process) closed a
given `OpenBreak`, when, or why; no revision history on an outcome object once
emitted; no log of an outcome changing from `Ambiguous` to `Verified` as new
evidence arrived. `Warrant` (line ~369 of `resolver_contract/types.py`) and
`rival_closure_count` on `Verified` are strong, but they record *why an
outcome was justified at the moment it was emitted* — the evidence, its
independence determination, contradictions — not a *history* of that
justification changing hands, being reviewed, or being overridden. Each run of
the resolver is a fresh, stateless computation over frozen input data; nothing
in `resolver/` or `corpus/oracle.py` persists a decision log across runs.

**maps to:** (a) evidence/version-control discipline for the benchmark
artifacts themselves — SHA-256 manifests plus a `git log`-verifiable
commit-ordering argument. **absent:** (b) a per-decision audit trail (who/when/why
a break was closed or a match revised) of the kind a production reconciliation
system's case-management log would carry — no such log exists.

---

## 4. 100%-population testing vs. sampling

**Present, and confirmed by direct code inspection — the strongest genuine
mapping alongside segregation of duties.**

`corpus/oracle.py`'s `score(output, truth)` function (from line 257) iterates
every gate over the complete set of outcomes the resolver produced, not a
sample:

- G1 (`Verified` wrong) loops `for outcome in output.line_outcomes` and checks
  every `Verified` instance's composition against ground truth, byte-for-byte
  (`claimed != actual`).
- G2 (independence) is checked inline on every `Verified` in the same loop.
- G3 (truth absent from a candidate set) loops every outcome again and checks
  every `Ambiguous` and every truncated `Unresolved`'s candidate set for the
  true composition.
- G4 (unwarranted assignment) loops `for row_id in output.row_assignments` —
  every assigned row, not a subset.
- G6 (declared provenance vs. corpus graph) loops every evidence item on every
  outcome.
- G7/G8 (abstention on a determined/reconstructible instance) run
  `output.abstention_failures(determined)` over the full `determined_instances(truth)`
  population.
- G9 (a `ProvenUnmatched` row that in fact settled) is described in
  `resolver_contract/types.py`'s `ProvenUnmatched` docstring as "a positive
  claim, gated at zero by G9," and `CLAIMS.md` reports it measured over **all
  701** proven-unmatched rows across **30 datasets**, not a draw from them.

`investigation/DERIVED_BRANCH_AUDIT.md`'s own framing header states the same
discipline in prose: "Every count is a full enumeration over all 30 datasets —
4,994 `CorrectlyUnmatched` claims — not a sample." `corpus/score_resolver.py`
(invoked via `--all`) iterates the dataset families
(`FAMILIES = ("datasets", "datasets_v2")`) and every axis point within them,
scoring each with the oracle — the run that produces `CLAIMS.md`'s numbers is
a full run across every generated dataset, every run, not a spot check.

Gates are exact-match, zero-tolerance by construction: G1 compares
`tuple(sorted(...))` row-id tuples for exact equality, not a fuzzy or
threshold-based comparison; G9 requires **0** settled rows among all proven
claims (`CLAIMS.md`: "**0** | 701 proven rows"). There is no gate anywhere in
`corpus/oracle.py` that accepts "close enough" or scores a sampled subset and
extrapolates.

**maps to:** COSO-style 100%-population testing (as distinct from statistical
sampling) — every gate scores every instance of its relevant population, every
run, with exact-match pass/fail rather than a tolerance band.

---

## 5. Materiality thresholds

**Absent, confirmed by search.**

A repo-wide search for materiality/threshold/tolerance language in
`resolver_contract/`, `corpus/oracle.py`, and `corpus/CORPUS_SPEC.md` turns up
exactly three hits, none of which is an amount-based materiality tier:

- `corpus/CORPUS_SPEC.md`'s "decoys colliding on **credit** + 1–2 paise
  near-collisions" row — this is a description of a *planted adversarial test
  case* (decoy amounts one or two paise off a real total, to test whether the
  solver is fooled), not a tolerance band the resolver or oracle is permitted
  to apply.
- `resolver_contract/RESOLVER_CONTRACT.md` line 356, describing G9 as
  "zero-tolerance" — this is the *absence* of a tolerance, stated explicitly.
- `resolver_contract/RESOLVER_CONTRACT.md` line 698, warning that a wrong
  design would make "every wrong answer a threshold-tuning exercise" — cited
  as a *rejected* approach, not an implemented one.

`Composition.__post_init__` and every gate in `corpus/oracle.py` compare
integer paise amounts for exact equality (`CLAUDE.md`: "Money is integer paise
everywhere. No float arithmetic."). There is no dollar/paise-amount-based
tiering anywhere — a one-paise discrepancy and a ten-lakh discrepancy are
scored by the identical zero-tolerance mechanism. A real reconciliation
control environment would typically define a materiality threshold below
which a break does not require investigation; nothing in this repo does that.

**absent: no amount-based materiality threshold or tiering exists anywhere in
`resolver_contract/` or `corpus/oracle.py` — every gate is exact-match
regardless of the amount at stake.**

---

## 6. Dual control / four-eyes approval

**Absent, confirmed by search — and must be kept separate from "two
independent evidence sources."**

A repo-wide search for approval-workflow language (`approve`, `four-eyes`,
`dual control`, `second signer`, `sign-off`, `maker-checker`) turns up no
implementation anywhere in `resolver/`, `resolver_contract/`, `matching/`,
`eval/`, or `corpus/`. The only hits are in unrelated research notes
(`research/03-track-risk-manager.md` on RBI's dispute-policy mandate,
`research/02-track-agentic-commerce.md` on a different track's proposed
agent-spend-approval design) and in agent-definition files describing this
project's own build process (`.claude/agents/recon-architect.md`,
`.claude/agents/red-team-panelist.md` — both about *this Claude Code agent's*
authority scoping, not about the reconciliation system under discussion).
None of it is a human two-person approval workflow inside the resolver or the
oracle.

**This must be distinguished carefully from what `Verified` actually
requires.** `Verified.__post_init__` (line ~659 of
`resolver_contract/types.py`) demands `self.warrant.has_independent_corroboration`
— at least two independent *source parties* (e.g. PSP and bank,
`SOURCE_PARTY` at line ~91) behind the evidence. That is a data-provenance
requirement: a claim needs corroboration from an independent *system of
record*, computed by `parties()` over `SOURCE_PARTY` groupings so that, for
example, `PSP_LEDGER` and `PSP_SETTLEMENT_REPORT` never count as two
independent parties (they are the same party, "psp"). It says nothing about
whether a *human* reviewed or approved the resulting `Verified` outcome before
it was reported. No code path in this repo pauses a decision for a second
person's sign-off, requires a distinct human role to approve an
`AttestationDiscrepancy` finding before it is surfaced, or blocks a `Verified`
outcome pending review. Every outcome in `resolver_contract/types.py` is
constructed and validated entirely by code, in one process, with no approval
gate.

**absent: no dual-control/four-eyes human approval workflow exists anywhere in
this repo; the "two independent parties" language in `Verified` is a
data-provenance requirement over evidence sources, not a human sign-off
requirement, and the two must not be conflated.**

---

## Summary table

| control category | present / absent / partial | strength of mapping |
|---|---|---|
| Segregation of duties | present | strong |
| Exception aging / break management | partial | adequate |
| Audit trail (benchmark integrity) | present | strong |
| Audit trail (per-decision, over time) | absent | none |
| 100%-population testing vs. sampling | present | strong |
| Materiality thresholds | absent | none |
| Dual control / four-eyes approval | absent | none |

*(Audit trail is split into two rows because the two senses genuinely diverge
— see §3.)*
