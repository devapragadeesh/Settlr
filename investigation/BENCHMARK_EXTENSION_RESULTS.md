# BENCHMARK_EXTENSION_RESULTS.md — what closing five named gaps found

Every number in this document was re-derived from the artefacts on disk
while writing it, not copied from earlier prose — the same discipline
`CHECKPOINT.md` states at its own opening. This document synthesizes; it
does not restate. Each finding below cites the generated artifact that is
its actual evidence.

## What this pass was for

`TEST_PLAN.md` lays out the plan; this is the results half. Five
workstreams, sequenced to respect this repo's own governing rule — corpus/
test work and resolver/matching code changes never land in the same
change — and its "ordering is the evidence" convention: `DECISIONS.md`
entries first, then generation, then scoring, never the reverse.

## 1. The wrong-bank-side direction holds

`corpus/BANKSIDE_RESULTS.md`: 2 of 2 planted bank-side errors drew
`AttestationDiscrepancy` from the resolver, the sound outcome, with all
oracle gates PASS and byte-identical verdicts across 3 runs. This is the
answer to README's own "largest remaining gap" — the evidence model's
"two independent parties" claim was written to be symmetric, and it
measures as symmetric. It was not previously measured in either direction
except the PSP-side one.

The frozen cascade cannot represent this outcome at all — it declines
(`Unresolved`) both corrupted lines, not because it checked and found
nothing wrong, but because "the sources disagree" has no name in its
vocabulary. This is not a defect in the frozen engine; it is the shape of
the gap between an evidence-tiered resolver and a cascade with no evidence
model, made concrete on two real lines instead of asserted in prose.

**A genuine imperfection surfaced and left visible, not smoothed over:**
`corpus/oracle.py`'s own `attestation_discrepancy` accounting — a measured,
ungated statistic — currently scores both of these correct detections as
`genuinely_false`, because its `planted` count is derived from a PSP-side-
only field. `DECISIONS.md` §54 records this and the decision to leave the
oracle uncorrected in this pass rather than widen it quietly. The scorer
prints the oracle's own number next to the re-attributed one, unresolved,
both visible.

## 2. Neither package can be tricked into a confident wrong answer by
   malformed input

`tests/adversarial/ADVERSARIAL_FINDINGS.md`: 40 corruption cases across both
packages, zero bucket-3 findings. This is a genuinely reportable negative
result, not an absence of testing — the suite tried duplicate keys, negative
amounts, truncated JSON, non-numeric fields, out-of-order timestamps, and
over-precision decimals, and in every case where a package produced an
answer at all, that answer was either correct or explicitly weaker than
confident (a decline, a discrepancy, an exception).

Four real asymmetries were found and are worth carrying forward even though
none crosses into "wrong answer": `resolver`'s paise parser silently
truncates a third decimal digit where `matching`'s rejects it outright; a
duplicate `settlement_id` in the PSP's settlement report is silently
last-write-wins in `resolver`'s loader; an unhandled `disputes.json` shape
silently empties `resolver`'s dispute set where `matching` raises; and a
dispute item missing both id fields collapses to a shared empty key. None
of these was patched in this pass — per this repo's own rule, they are
findings, not fixes, and belong in a future change that is *only* about
`resolver`/`matching` source.

## 3. The frozen cascade's "does not scale" claim is now measured, not
   asserted

`scale/SCALE_REPORT.md` existed only as an unrun scaffold before this pass.
It now shows the degradation boundary landing exactly where
`SETTLEMENT_SPEC.md` §1.5 predicted it (`max_pool = 28`), the solver-side
enumeration truncation setting in progressively above that, and a concrete
980-second/48,566-row data point with a named, correct next engineering
step (column-generation decomposition) rather than a vague "raise the time
limit." Resolver throughput at scale remains genuinely unmeasured — not
because it was avoided, but because measuring it honestly requires new
corpus-format data at large pool sizes, which this pass's own scope rule
correctly kept out of a change that also touches corpus generation
elsewhere.

## 4. The apparatus still holds together end to end

32/32 datasets (30 original + 2 new) pass their own leak audit. The full
suite passes clean from a genuinely fresh clone (830 passed, 27 skipped).
`git status` across this entire pass confirms zero lines changed in
`resolver/*.py`, `matching/*.py`, or any frozen `engine/` path — every
finding this pass produced is a documented finding, not a silent patch.

## 5. The repo's "generated, cannot drift" claim holds cold, not just warm

`investigation/OPERATIONAL_REVIEW.md`: every README "Run it" command
succeeded verbatim in a clean clone with no unexpected output.
`run_all.py`'s documented ~63m42s reproduced to within 10 seconds.
`CLAIMS.md` reproduced byte-for-byte; `SCORECARD.md` reproduced byte-for-
byte except its own runtime figure, which is expected to vary with machine
load and is not an accuracy claim. This had never actually been tested
against a cold clone before — only inside the long-lived development tree.

## 6. Where this repo's controls posture actually stands, honestly

`investigation/CONTROLS_MAPPING.md` (read with its own banner: informational,
not a compliance certification). Two genuinely strong mappings — segregation
of duties (AST-enforced isolation tests) and 100%-population testing
(the oracle scores every instance, every run, no sampling) — and two
explicit absences named without padding: materiality thresholds and dual-
control/four-eyes human approval. Both are real gaps against standard
reconciliation-system practice, stated as gaps rather than argued away.

## What this pass adds up to

Before this pass, README's own Limitations section listed several
self-identified, unmeasured gaps. After it: the largest one (wrong-bank-side)
is measured and holds; malformed-input robustness is measured and holds
with zero silent-wrong-answer findings and four honestly-documented
asymmetries; the frozen cascade's scaling ceiling is measured, not asserted;
the whole apparatus is confirmed to reproduce from a cold clone, not just a
warm dev tree; and the project's controls posture is mapped against industry
practice with its genuine strengths and genuine absences both stated
plainly. Nothing here was patched into looking better than it measured —
every wrong-shaped finding (the oracle's PSP-side-only accounting, the four
loader asymmetries) is written up and left for its own change, per this
repo's own rule that discovering a defect while doing something else is not
a license to fix it there.

What remains open, by design: the GST/ITC axis, the full B×C grid,
`split-credit`, resolver throughput at scale, and any global financial-
conservation test. These were declared out of scope before this pass began,
for reasons stated in `TEST_PLAN.md`'s "Scope boundary" section, and staying
declared is what keeps that boundary meaningful.

## Addendum: the GST/ITC axis — 2026-08-31, `DECISIONS.md` §55

The GST/ITC axis named above as remaining open has since been closed, in a
separate, dated, later pass — see `TEST_PLAN.md`'s own addendum and
`corpus/GST_RESULTS.md` for the full measurement. In one sentence: a real
population replaces the old fixed 3-line trick, invoice identification
against it is exact on every statutory ground measured, but the
`itc_availability` shortcut and the absent-from-2B rupee total both do not
generalize — and neither finding licenses any claim of GST/ITC reasoning in
`resolver/`, which a read-only probe confirms never opens the file at all.
The remaining four items in the paragraph above — the full B×C grid,
`split-credit`, resolver-at-scale, global conservation tests — are
unaffected and still open.
