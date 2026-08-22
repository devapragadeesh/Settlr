# scale/ — throughput fixtures

**Runtime only. No accuracy claim is made on anything in this directory.**

## Why this exists

"Throughput" is the first word in Track 04's bar, and until Phase 4 this
project had no number for it. `eval/EVAL_REPORT.md` reported ~1.4s on 240 rows,
which is a latency figure on a toy volume, not a throughput claim.

## Why it is a separate artifact from the held-out evidence

These datasets are generated at a **different seed** from the held-out set
(`41`, not `20260905`) and are never scored. That separation is deliberate and
is enforced, not merely intended:

- `eval/scale_report.py` computes no accuracy metric at all — no `score()`,
  no `match_rate`, no precision, no recall — and
  `tests/test_scale_degradation.py::test_the_scale_fixtures_are_never_used_for_an_accuracy_claim`
  fails the build if that changes.
- `holdout/HOLDOUT_RESULTS.md` reads nothing from here.

A throughput fixture folded into an accuracy result is how a benchmark stops
meaning anything: pick the volume that scores best and report it as the
headline. Keeping them apart costs one directory and removes the option.

## What is held constant, and why

The batch cadence stays at the primary set's **12 weekly cut-offs** across
every volume, rather than scaling with it. That makes **eligible pool size the
independent variable** — the quantity `SETTLEMENT_SPEC.md` §1.5 bounds, and the
one whose growth these runs exist to observe. Scaling the cadence too would
have held pool size roughly constant and measured nothing.

The consequence is worth naming: 50,000 rows across 12 weekly batches is a
higher per-batch concentration than a real merchant of that volume would have,
because a real merchant settles daily. This overstates the pool-size pressure
relative to volume, and understates how far the approach would carry with a
daily cadence. Stated here rather than left for someone to notice.

## Layout

| path | contents |
|---|---|
| `generate_scale.py` | drives the **frozen** `engine/generator.py` as a library with `ROLES` rebound |
| `MANIFEST.json` | one record per volume: rows, batches, pool sizes, degradation counts |
| `data_<N>/`, `truth_<N>/` | the generated fixtures |
| `scale_results.json` | raw per-volume runtime measurements |
| `SCALE_REPORT.md` | the written report, produced by `eval/scale_report.py` |

## Reproducing

    python3 scale/generate_scale.py
    python3 eval/scale_report.py

`scale_report.py` caches completed volumes in `scale_results.json`, so an
interrupted run resumes rather than restarting.
