# OPERATIONAL_REVIEW.md — a cold-clone walkthrough, timed

Every number below was either freshly measured against a genuine clean
`git clone` of this repo (never the long-lived dev tree), or is explicitly
cited from the repo's own prior documentation and never conflated with a
fresh measurement. Where a step is not stated as "documented", it was run
here, once, on 2026-08-31, on this machine.

Clone location: a scratch directory outside the working tree
(`/private/tmp/.../opreview/clone`), `git clone /Users/deva/razorpay clone`.
Because clone is local-path from working-tree HEAD, it clones the
**committed** state only — none of this pass's own uncommitted new files
(`corpus/datasets_bankside/`, `tests/adversarial/`, `scale/SCALE_REPORT.md`,
the `DECISIONS.md` §51-§54 additions) are present in it. That is correct for
this exercise: it verifies the *existing, already-published* repo's
operational ease, not this pass's in-flight additions.

## 1. Setup

```
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

**11.6s wall clock, exit 0, no warnings beyond pip's own "new release
available" notice.** No version-pin gaps, no OS-specific wheel failures for
`ortools`/`scipy`/`rapidfuzz` on this machine (macOS, Python 3.14).

## 2. Hash verification

```
shasum -a 256 -c <(sed 's|^\([0-9a-f]*\) |\1  |' engine/DATASET_HASHES.txt)
```

Output: all 6 primary files `OK`
(`recon_combined.json`, `disputes.json`, `bank_statement.csv`,
`erp_orders.csv`, `gstr2b.csv`, `ground_truth.json`), plus exactly the one
documented `shasum: WARNING: 1 line is improperly formatted` — **no other
unexpected output.** This matches README's stated expectation exactly.

```
for f in corpus/datasets*/*/DATASET_HASHES.txt; do (cd "$(dirname "$f")" && shasum -a 256 -c DATASET_HASHES.txt); done
```

**30/30 corpus dataset directories verify clean**, no warnings, no failures.

## 3. Full test suite

```
pytest tests engine/tests corpus/tests resolver/tests -q
```

**830 passed, 27 skipped, 244.83s (4:05.57 wall clock), exit 0.** README's
listed command runs clean from a genuinely fresh clone. Note:
`tests/adversarial/` (new in this pass, uncommitted) is not in this list and
so was not part of this run — that suite is scored separately in this pass's
own artifacts, not folded into README's baseline command.

## 4. The four "individual pieces" commands

| command | wall clock | result |
|---|---:|---|
| `python3 -m resolver.run --all` | 21:08.49 | TOTAL row: 275 Verified, 62 AttestationDiscrepancy, 1 Reconstructed, 6 Ambiguous, 255 Unresolved — matches `SCORECARD.md`'s cited totals exactly (see §5) |
| `python3 corpus/triviality_check.py --all` | 0.18s | `verdict counts: {'TRIVIAL': 15, 'PARTIAL': 13, 'NOT TRIVIAL': 0, 'N/A': 2}` |
| `python3 corpus/leakage_audit.py --all` | 2:56.21 | `30/30 datasets pass their own leak audit` |
| `pytest tests engine/tests corpus/tests resolver/tests -q` | 4:05.57 | see §3 |

All four run clean from the fresh clone, matching README's "Run it" section
verbatim, in order, with no manual intervention beyond `source .venv/bin/activate`.

## 5. `run_all.py`, timed

```
time python3 run_all.py
```

**1:03:52.46 wall clock (3820.77s user, 99% CPU), exit 0.**

`run_all.py`'s own module docstring states: *"Expect roughly an hour;
measured end to end in a clean checkout at 63m42s."* This fresh run:
**63m52s** — 10 seconds off a previously-documented clean-checkout figure.
This is the closest possible confirmation that the documented number was
itself a genuine measurement and that it reproduces, not a coincidence of
rounding.

## 6. Spot-check: do the generated numbers actually reproduce byte-for-byte?

`diff` between the live repo's committed `SCORECARD.md`/`CLAIMS.md` and the
versions this fresh `run_all.py` run generated in the scratch clone:

- **`CLAIMS.md`: zero-diff, byte-identical.**
- **`SCORECARD.md`: one line differs** — `resolver runtime, 30 datasets`:
  committed value `1446s`, this run's value `1264s`. Everything else on the
  page, including every accuracy/gate figure (0 wrong `Verified`, 0 wrong
  `ProvenUnmatched`, 701 `ProvenUnmatched`, 239/275 non-decisive `Verified`,
  62 `AttestationDiscrepancy` reported / 0 genuinely false, 275/275 answered
  on the 28 PSP-present datasets, 1/24 on the 2 PSP-absent datasets, all 15
  abstentions correct refusals) is **byte-identical**.

The one line that moved is a wall-clock timing figure — expected to vary
with machine load between runs, and explicitly not an accuracy claim. Every
accuracy/gate number on the "five-minute read" reproduces exactly in a
genuinely clean environment, which is what "generated, cannot drift" is
supposed to mean and, measured here, does mean.

## 7. Orphaned artifacts from this testing pass

As of this walkthrough, three new artifacts this pass produced —
`scale/SCALE_REPORT.md`, `corpus/BANKSIDE_RESULTS.md`, and
`tests/adversarial/ADVERSARIAL_FINDINGS.md` — are **not yet referenced from
any front-door document** (README's layout section, `CHECKPOINT.md`). A
first-time reader following README's existing "Layout" section would not
discover any of them. This is expected at this exact point in the pass —
this operational review runs before the two closing deliverables
(`TEST_PLAN.md`, `investigation/BENCHMARK_EXTENSION_RESULTS.md`) are
written, and those two documents are precisely what is meant to point a
reader at all three. It is recorded here as a finding rather than silently
fixed by this document, per this pass's own discipline: an operational
review reports, it does not repair.

## 8. Summary

Every command in README's "Run it" section, executed verbatim in order in a
genuinely clean clone, succeeded with no unexpected output. The one
previously-documented long-running figure (`run_all.py`, ~an hour) reproduced
to within 10 seconds. Every accuracy/gate number on `SCORECARD.md` and every
figure on `CLAIMS.md` reproduced byte-for-byte; only a runtime measurement
(expected to vary) did not. The repository's own "generated, cannot drift"
claim holds under a fresh, cold-clone test, not just inside the long-lived
development checkout.
