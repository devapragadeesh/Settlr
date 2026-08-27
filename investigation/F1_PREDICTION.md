# F1 — committed prediction, written before the fix exists

`resolver/eligibility.py:73` excludes rows from the pool on `on_hold`, a
**current-state snapshot**, when building the pool as at a **past**
`value_date`. `DECISIONS.md` §44 instance F1.

The fix is to delete the filter. This file is committed **before** that
happens and before any oracle run scores it. `git log` is the evidence.

## Why it is being fixed although it bites nothing today

Measured across all 30 datasets: **0 rows carrying `on_hold == True` appear in
any true composition.** The predicate is correct here by a property of the
generated data, not of the rule.

That is defect D2's shape verbatim — a branch whose safety came from the data,
inside a passing suite, right up until held-out data moved 50 rows
(`investigation/DEFECT_REPORT.md`). And `resolver/eligibility.py`'s own
docstring promises the opposite of what the filter does: it says the module
"errs LARGE" where rules are uncertain and returns "a superset of the true
one, which is the safe direction". This filter errs **small**.

## The measured input change

Removing the filter grows every pool by the eligible held rows.

| | |
|---|---:|
| mean pool growth | **+1.7%** |
| max pool growth, any dataset | **+2.8%** |
| row-slots added across all pools, all datasets | **1,544** |
| largest pool anywhere | **764 → 777** |
| held rows per dataset | 3 – 15 |

The change is small. Enumeration cost is exponential in pool size, so a small
change is not necessarily a small effect, and that asymmetry is the reason for
predicting rather than assuming.

## The prediction

| quantity | now | predicted | reasoning |
|---|---:|---|---|
| **G3** — truth absent from candidate set | 20 | **20–24, equal or worse** | the truth is unchanged and was always reachable, since no held row is in any true composition — so added rows cannot *remove* the truth. They can add rivals and drive the enumeration into the cap before the truth is reached. Cannot improve. |
| **G8** — abstention on reconstructible instances | 15 | **15–18, equal or worse** | more rows ⇒ more closing subsets ⇒ more `Ambiguous` / `Unresolved(enumeration_truncated)`. There is no mechanism by which a larger pool produces *more* unique closures. Cannot improve. |
| **datasets newly FAILING** | — | **0** | the 28 passing datasets are attested; Tier A resolves from the attestation and never consults `pool_at` for a composition. Residual risk is via `_tier_b` (`resolve.py:564`), which does test pool membership. |
| **`ProvenUnmatched`** | 699 | **699 exactly** | see below |
| **G9** — proven rows that settled | 0 | **0 exactly** | see below |
| **`OpenBreak`** | 4,295 | **4,295, or higher by at most the rows held by the 2 `Reconstructed`** | if larger pools destroy those two reconstructions, their rows return to the unmatched population |

### Why `ProvenUnmatched` and G9 cannot move

Both `ProvenUnmatchedReason`s are computed in `resolver/breaks.py` from the row
set alone — `NOT_CAPTURED` is `credit == 0`, `NETTED_OUT` is refund arithmetic
against `eligible_at`. **Neither reads a pool.** The population they range over
is *rows not in `assigned`*, and `assigned` is `Verified` (attestation-driven,
pool-independent) plus `Reconstructed` (2 instances across 30 datasets).

Even in the worst case where both reconstructions are destroyed, their rows
return to the unmatched population — and those rows **settled**, so they cannot
become `ProvenUnmatched`: a netted-out or uncaptured row does not settle. G9
therefore has no path to a violation from this change.

If either figure moves, the reasoning above is wrong and that is the finding.

## What would make this a bad fix

If G8 or G3 degrade by more than a few violations, the honest conclusion is
that the *superset* discipline costs measurable accuracy at PSP absence, and
that trade is reported rather than reversed. **No tuning after the score.**

---

# Result — run 2 (before) against run 3 (after)

Written after the oracle ran once against the fix committed in `4b65764`.
The prediction above was committed in `427aea6`, before the fix existed.

## Misses first: one prediction was wrong

**`ProvenUnmatched` was predicted at "699 exactly" and came in at 701.**

The reasoning behind that "exactly" is quoted from above:

> Even in the worst case where both reconstructions are destroyed, their rows
> return to the unmatched population — and those rows **settled**, so they
> cannot become `ProvenUnmatched`.

The clause "those rows settled" is an **unexamined assumption that the
assignment being destroyed was a true one**. One of the two `Reconstructed`
was the resolver's only wrong answer — an adoption of a foreign bank line at
`datasets/A20_B50_Cmax` — so its rows had never settled at all, and two of
them are entailed `NOT_CAPTURED` / `NETTED_OUT`. G9 stayed at 0, which
confirms they genuinely never settled.

Predicting a population by reasoning about what it excludes requires knowing
whether the excluding claim was *correct*, and the prediction did not check.

## What the fix did

| gate / quantity | run 2 (before) | run 3 (after) | predicted | verdict |
|---|---:|---:|---|---|
| **G3** truth absent from candidate set | 20 | **20** | 20–24, equal or worse | ✅ |
| **G8** abstention on reconstructible | 15 | **15** | 15–18, equal or worse | ✅ |
| **G9** proven rows that settled | 0 | **0** | 0 exactly | ✅ |
| G1, G2, G4, G6 | 0 | **0** | — | ✅ |
| datasets FAILING | 2 | **2** | 0 newly failing | ✅ |
| `ProvenUnmatched` | 699 | **701** | **699 exactly** | ❌ **wrong** |
| `OpenBreak` | 4,295 | **4,308** | 4,295 or higher | ✅ |
| `Verified` | 275 | 275 | — | unchanged |
| … non-decisive | 238 | 239 | — | +1 |
| **`Reconstructed` wrong** | **1** | **0** | not predicted | see below |
| `Reconstructed` correct | 1 | 1 | — | unchanged |
| `Ambiguous` | 5 | 6 | — | +1 |
| `Unresolved` | 255 | 255 | — | unchanged |
| `AttestationDiscrepancy` | 62 | 62 | — | unchanged |
| clustered rows / distinct causes | 1,573 / 54 | 1,582 / 54 | — | +9 rows |

`OpenBreak` by reason: `upstream_unresolved` 1,573 → 1,582, `unexplained`
1,469 → 1,472, `unexpected_change` 303 → 304, `timing_difference` unchanged.

## The unpredicted result, which is the interesting one

**The fix eliminated the resolver's only wrong answer.**

`datasets/A20_B50_Cmax` held a `Reconstructed` that adopted a bank line which
is not a settlement of ours. With the held rows restored to the pool, that
line acquired a **rival closing subset** and the outcome fell to `Ambiguous` —
*here are the candidates* rather than *here is the answer*.

That is the mechanism the superset invariant exists for, working in the
direction the docstring predicts: a pool that is too small hides rivals, and a
hidden rival is indistinguishable from no rival. The wrong answer was not
caused by bad arithmetic; it was caused by **not being shown the alternative**.

This was not predicted and is not claimed as a design intention. It is one
instance, on one line, in one dataset.

## What it cost

Nothing measurable. No gate moved, no dataset changed verdict, `Verified` and
`Unresolved` are identical, and the enumeration absorbed a mean +1.7% pool
growth without a single new truncation.

The prediction allowed for G3 and G8 to degrade and said that trade would be
reported rather than reversed. It did not arise.

## Honest scope of "0 wrong answers" after this run

Across 30 datasets: **G1 = 0** (no wrong `Verified`), **G9 = 0** (no
`ProvenUnmatched` row settled), and `Reconstructed` wrong = 0.

That last figure is over a population of **one**. `Reconstructed` occurs once
in the entire corpus, so "0 wrong out of 1" carries no information about a
rate, and the previous run's "1 wrong out of 2" carried none either. Both are
reported as counts, and neither should be read as accuracy.
