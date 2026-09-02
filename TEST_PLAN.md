# TEST_PLAN.md — closing this repo's own named gaps

Every number cited below lives in the artifact it is cited from; none is
retyped here. This document is the plan and the map — the numbers are in
`corpus/BANKSIDE_RESULTS.md`, `tests/adversarial/ADVERSARIAL_FINDINGS.md`,
`scale/SCALE_REPORT.md`, `investigation/OPERATIONAL_REVIEW.md`,
`investigation/CONTROLS_MAPPING.md`, and the existing `SCORECARD.md`/
`CLAIMS.md`. The synthesis of what all of it means is
[`investigation/BENCHMARK_EXTENSION_RESULTS.md`](investigation/BENCHMARK_EXTENSION_RESULTS.md).

## Why this document exists

`README.md`'s own Limitations section names its unclosed gaps explicitly: no
wrong-*bank*-side error class ("the largest remaining gap"), an unrun
`scale/` scaffold, no adversarial/malformed-input testing anywhere, and — as
background — three unfixed defects in the frozen cascade and an oracle that
cannot pass all its gates on the PSP-absence datasets. This is a hiring
artifact; leaving a self-named gap unexamined reads worse than a closed gap
that turned out badly. This plan closes the highest-value subset of those
gaps and reports honestly on what closing them found, per `DECISIONS.md`
§51-§54.

Two things this plan deliberately did **not** attempt, decided with the
project owner before work began: the GST/ITC axis (README already states
plainly that no GST claim in this repository is demonstrated, and this pass
does not change that), and the full 60-cell B×C axis grid (14/60 cells
remain run). A new global financial-conservation test suite (e.g.
`sum(matched) == sum(ledger)` across the whole corpus) was offered and
explicitly declined — the per-credit balance identity is already
unfalsifiable by CP-SAT construction (README's own "Deliberately not
reported" section) and a global sum-check has the same shape of problem.

**Amended 2026-08-31 (`DECISIONS.md` §55).** The GST/ITC axis named above as
deliberately deferred has since been built, as a separate, later, dated
pass — `corpus/datasets_gst/`, scored read-only against the frozen filters
in [`corpus/GST_RESULTS.md`](corpus/GST_RESULTS.md). The B×C grid gap and
the global conservation-test decision are unaffected and stand as written.

## 1. Accuracy — does the resolver's evidence model actually hold in a
   direction it was never tested in?

Every existing planted record error in the 30-dataset corpus corrupts the
**PSP's** attestation. `AttestationDiscrepancy`'s own contract text is
already symmetric ("the sources disagree… a finding about the record, not a
claim about which rows settled"), but that symmetry had never been tested
from the other direction: a bank credit that disagrees with a **correct**
PSP attestation.

**What was built.** A new planted-error class, `mispost` (`DECISIONS.md`
§51), corrupts one bank-statement line's amount while leaving
`settlement_report.csv`/`recon_combined.json` correct and untouched. Two new
datasets, `corpus/datasets_bankside/`, scored separately from the existing
30-dataset aggregate by `corpus/score_bankside.py` (§51's own rejected
alternative: folding it into `three_systems.py`'s `FAMILIES` tuple, which
would have meant rewriting hardcoded dataset-count prose across three
already-cited documents for a two-dataset addition).

**Result:** see `corpus/BANKSIDE_RESULTS.md`. 2 of 2 planted bank-side errors
are handled soundly by the resolver — `AttestationDiscrepancy`, not a wrong
`Verified` — with all oracle gates passing and the verdict byte-identical
across 3 runs. The frozen cascade, by contrast, has no outcome that can
represent "the sources disagree," so it lands on `Unresolved` on both —
bounded above by "declined," by construction, not by a failure. One real
side-finding surfaced while building this: `corpus/oracle.py`'s measured
`attestation_discrepancy` accounting derives `planted` from a PSP-side-only
field, so a correct bank-side detection currently scores as
`genuinely_false` in the oracle's own uncorrected output — recorded and
explained rather than silently patched (`DECISIONS.md` §54).

Deliberately not built in this pass: `split-credit` (one settlement posted
as two bank lines) — it may expose a genuine question the outcome vocabulary
doesn't yet answer, and extending `resolver_contract` mid-pass is explicitly
against this repo's own rule (§51).

## 2. Financial loopholes / instability — does either package degrade
   safely on garbage?

**What was built.** `tests/adversarial/` (`DECISIONS.md` §52): 22 resolver
cases and 18 matching cases, each a single-field corruption of one minimal
valid dataset, fed read-only through `load()` and the resolve/cascade entry
point. Every case sorts into exactly one of three buckets — clean typed
decline, uncaught low-level exception (allowed, cataloged), or a silent
confident wrong answer (the only bucket that fails the suite).

**Result:** see `tests/adversarial/ADVERSARIAL_FINDINGS.md`. **Zero
bucket-3 findings** on either package, across all 40 cases —
`pytest tests/adversarial -q` passes 93/93. No malformed input produced a
confident `Verified`/`Determinate` from corrupted data. Four real behavioral
asymmetries were surfaced and documented anyway, because they are true and
worth knowing even though none is a wrong-answer defect: `resolver.loaders`
silently truncates over-precision decimal amounts where `matching.money`
rejects them; `resolver`'s settlement-report loader is silently last-write-
wins on a duplicate `settlement_id`; a `disputes.json` in an unhandled shape
silently empties `resolver`'s dispute set where `matching` raises a
`KeyError`; and a dispute item missing both id fields maps to a shared empty
key with a latent (untested at scale) collision risk.

## 3. Throughput — was the frozen cascade's "does not scale" claim ever
   actually measured?

**What was run.** The existing `scale/generate_scale.py` +
`eval/scale_report.py` scaffolding, unmodified, to completion, across all 8
documented size points (`DECISIONS.md` §53).

**Result:** see `scale/SCALE_REPORT.md`. Comfortable to ~246 rows (pools
under the documented `max_pool = 28` ceiling, everything determinate, sub-
2-second). Degradation — both simulator-side (FIFO fallback) and solver-side
(enumeration truncation) — measured directly, not predicted: first fires at
505 rows, ceiling straddled exactly at the documented boundary (largest
undegraded pool 25, smallest degraded pool 29). At 48,566 rows: 980s wall
clock, worst single line 143s. The report names the correct next step
(column-generation / set-cover decomposition, not a bigger time budget) and
two cheap mitigations that are not the same as solving it. Resolver
throughput at scale is explicitly **not** measured in this pass — `scale/`'s
fixtures are frozen-generator CSV shape, `resolver/loaders.py` reads only
corpus-generator JSON shape, and closing that gap means a new corpus-format
generation run, which is corpus work and out of scope alongside this pass's
other corpus changes (§53).

## 4. End-to-end wiring — does the whole apparatus still hold together?

`corpus/leakage_audit.py --all` and `corpus/triviality_check.py --all` both
pass with the new `datasets_bankside` family included (32/32 leak audit;
triviality verdict counts unchanged in shape). The full suite —
`pytest tests engine/tests corpus/tests resolver/tests -q` — passes clean
(830 passed, 27 skipped) from a genuinely fresh clone, not just the dev
tree. `git status` confirms no commit in this pass touched `resolver/*.py`,
`matching/*.py`, or any frozen `engine/` path.

## 5. Ease of use — does a first-time reader's cold clone actually work?

See `investigation/OPERATIONAL_REVIEW.md` for the full, narrative, timed
walkthrough: every command in README's "Run it" section, run verbatim in a
clean clone, succeeded with no unexpected output. `run_all.py`'s documented
"~63m42s" figure reproduced to within 10 seconds (63m52s, fresh). Every
accuracy/gate figure on `SCORECARD.md` and `CLAIMS.md` reproduced byte-for-
byte in the clean clone — only a runtime figure (expected to vary with
machine load) differed. One finding: the three new artifacts this pass
produced are not yet linked from any front-door document — this document and
`BENCHMARK_EXTENSION_RESULTS.md` are what closes that.

## 6. Industry-standard controls mapping

See `investigation/CONTROLS_MAPPING.md` in full — it carries its own
"informational, not a compliance certification" banner and must be read with
it. Summary: segregation of duties and 100%-population testing (COSO-style)
are strong, genuine mappings, backed by AST-enforced isolation tests and an
oracle that scores every instance of every dataset every run. Audit trail is
strong for the benchmark's own integrity (SHA-256 manifests, git-log
ordering) but explicitly absent for per-decision history (no log of who/when
/why a specific break was closed). Exception aging exists as a real,
populated field (`OpenBreak`) but is a static snapshot, not a live SLA
clock. Materiality thresholds and dual-control/four-eyes approval are both
explicitly **absent** — stated plainly rather than padded with a strained
analogy.

## Scope boundary, restated

What this pass closed: a wrong-bank-side dataset class (mispost only),
malformed-input robustness testing for both packages, the frozen cascade's
throughput measurement, a cold-clone operational verification, and an
industry-controls mapping. What it did not attempt, on purpose: the GST/ITC
axis (closed in a later, separate, dated pass — `DECISIONS.md` §55,
`corpus/GST_RESULTS.md`), the full B×C grid, `split-credit`, resolver
throughput at scale, and global financial-conservation tests. What it found
but did not fix, on purpose, per this repo's own governing rule against
mixing corpus/test work with resolver code changes in the same pass: the
oracle's PSP-side-only attestation-discrepancy accounting (`DECISIONS.md`
§54), and the four adversarial-suite behavioral asymmetries above.

## Addendum: the GST/ITC axis — 2026-08-31, `DECISIONS.md` §55

Named above as deliberately out of scope for the original pass, then closed
in a dedicated follow-up: `corpus/datasets_gst/` (2 datasets) replaces the
fixed, always-identical 3-index ITC plant with a real, seeded, fractional
population over the gateway's own 2B lines — a genuine partial-filing
fraction, a genuine IRN-presence fraction, drawn independently so a single
invoice can carry more than one statutory ground, plus vendor-pool noise
varied independently of population size. Scored read-only against the
existing, unmodified `matching/stage4_exceptions.py` filters and against
`resolver/` in [`corpus/GST_RESULTS.md`](corpus/GST_RESULTS.md). The result
is one of the two honest outcomes named in advance: the filters do **not**
fully generalize — the `itc_availability` single-column shortcut misses
every Rule-37A-only and absent-from-2B invoice by construction, and the
absent-from-2B ground's rupee total disagrees with ground truth even where
invoice identification is exact on every ground measured. Per the same
governing rule as everything else in this document, this finding was written
up, not patched into `matching/stage4_exceptions.py`. This pass measures the
**benchmark** and the **existing frozen filter's** behavior against it.

**Two sentences of the paragraph above have since been superseded, and both
are corrected here rather than left to age:**

* This paragraph originally described the absent-from-2B rupee disagreement
  as **structural** — "between an accrued and an aggregate figure". That is
  false and `DECISIONS.md` §66 retracts it. The disagreement is a **defect in
  the corpus generator**: `corpus/generator/build.py:681` puts the full fee of
  zero-GST rows into the gateway invoice's taxable value and charges 18% on
  it, while both consumers correctly exclude those rows. Rounding is a real
  but secondary term of 1–8 paise. See `corpus/GST_RESULTS.md`'s decomposition
  table.
* This paragraph originally said a probe confirms `resolver/loaders.py`
  **never opens** `gstr2b.csv`, and that GST reasoning in `resolver/` "remains
  unattempted". Both were true when written and are **no longer true**:
  `DECISIONS.md` §59 gave the resolver the tax feed, and `OpenBreak` now
  carries `itc_risk`/`itc_risk_grounds`. The probe still runs, but its
  question changed — it now asserts that removing `gstr2b.csv` leaves every
  line outcome identical, i.e. that the feed may annotate an open item and may
  never reach a composition. §60/§64 measure what the annotation achieves.

---

## Addendum: status of §56–§69, as of 2026-09-02

The sections above describe work through `DECISIONS.md` §55. What follows is a
**status record only** — every number lives in the artifact named beside it,
and nothing is retyped here. It exists because this document is the map, and a
map that stops eleven decisions short of the territory misleads more than no
map at all.

| § | what it is | status |
|---|---|---|
| §56–§57 | oracle bank-side attestation accounting, then narrowed to a declared per-line contradiction | **done** — `corpus/BANKSIDE_RESULTS.md` |
| §58 | `resolver/enumerate_closures.py` budgets in WALL-CLOCK seconds — documented, deliberately not fixed | **superseded by §67/§68** |
| §59 | GST evidence reaches `resolver/`, may only ever annotate an `OpenBreak` | **done** |
| §60 | ITC-risk flag measured, **not gated** | **done, gate still open** — see below |
| §61 | ITC-risk flag gated on the ROW's own settlement, not its month's | **done** |
| §62, §65 | two generated-prose bugs in `score_gst.py`, found by reading the reports | **done** |
| §63 | resolver+oracle GST code frozen by content hash before any held-out data existed | **done** |
| §64 | the held-out GST run — freeze held, gates clean, `precision 1.0 / recall 0.75` | **done; the miss is diagnosed but NOT fixed** — see below |
| §66 | `gstr2b_absent` gap is a generator defect, not the published "structural" rounding artefact | **done** — prose corrected, generator deliberately not touched |
| §67 | the §58 prediction, committed **before** the fix | **done** — `investigation/resolver_nondeterminism/PREDICTION.md` |
| §68 | the §58 fix: `max_deterministic_time`, and the frame-mixing predicate it forces closed | **in progress** — before/after pair captured, determinism verification running |
| §69 | composition-cardinality reporting vocabulary (1:1 / N:1 / N:N) | **done** — `corpus/score_resolver.py` |

### What is knowingly still open, stated plainly

**The G10 gate on `itc_risk_flag` does not exist.** §60 chose measure-don't-gate
because gating an untested first measurement is what G5 was withdrawn for. The
held-out run has since supplied a reference number, so the gate is now
*possible* — and it is still not written. It is queued behind §68's numbers
stabilising, because a gate set against figures that are about to move is a
gate set against noise.

**The §64 false negative is diagnosed and deliberately unfixed.** The missed
row is `rfnd_bJNvTaslE4EpW0` — a **refund**, `fee = 0`, `tax = 0`. The
resolver declined to flag it correctly: a refund generates no gateway fee, so
there is no input tax on it to be at risk, and
`corpus/generator/build.py` never puts a refund into the invoice either. The
disagreement is in `corpus/oracle.py`'s truth set, which counts every row that
merely *settled in* an at-risk month — the exact reading §61 rejected on the
resolver side and never applied to the measurement side.

That diagnosis is recorded and **not acted on**, on purpose. Correcting the
oracle would move a held-out number from `recall 0.75` to `1.0`, and "the
measurement was wrong, my code was right" is the most self-serving conclusion
available on a held-out miss. If the oracle is corrected, the corrected figure
is published *alongside* §64's, never in place of it: §64's number stands as
measured under the definition in force when it was taken.

**The B×C grid gap and the declined global conservation test** stand exactly as
written above. Nothing since §55 changes either.
