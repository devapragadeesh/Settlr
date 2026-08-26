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
