# CHECKPOINT — Settlement Truth Engine, benchmark corpus phase

**Written 2026-08-24. Branch `corpus-benchmark`, head `5460752`.**

Every number in this document was re-derived from the artefacts on disk while
writing it, not copied from earlier prose. Where that re-derivation contradicted
something this project had already published, the contradiction is reported in
§6 rather than quietly fixed.

---

## 0. Two findings that change the conclusions of everything below

Both were surfaced by an adversarial review of this phase and then **verified
independently against the data before being written down**. Both are serious.
They are placed first because reading §4–§8 without them gives a materially
wrong impression of what the corpus measures.

### 0.1 A fifteen-line resolver scores 168/168 on the entire corpus

`corpus/baseline_naive.py`. Group the recon rows by `settlement_id`, net
credit − debit, match the total to a bank credit. No solver, no enumeration, no
contract.

| measured across all 14 datasets, 280 bank lines | |
|---|---:|
| compositions exactly correct | **168 / 168** |
| bank line → batch correct | **168 / 182** (the 14 misses are reversal debits) |
| foreign lines correctly rejected | **98 / 98** |
| abstentions on 88 determined + 31 reconstructible instances | **0** |

Invariant across pool size 10 → 60, coverage 100% → 0%, and all three selection
rules.

**Why:** `settlement_id` is populated on every settled row of every dataset, and
**the corpus never once plants a false `settlement_id`.** The 13 planted
`wrong_attestations` corrupt a scalar amount in `settlement_report.csv`; not one
assigns a row to the wrong batch. A resolver that simply trusts the PSP is
therefore perfectly calibrated here, and the corpus cannot tell it apart from a
sound one.

**What this does to the results below:**

* **Axis A does not measure difficulty.** The closure collapse in §4.3 is real
  arithmetic, but it only *binds* a solver that has withheld `settlement_id`
  from itself. The difficulty is constructed by the engine under test.
* **Axis B does not remove the composition claim.** It varies the bank-line →
  batch *reference*. `settlement_id` is at 100% in every cell.
* **"Abstained on 49 of 88" is measured against a bar a `GROUP BY` clears.**

The epistemic argument for distrusting an attestation is still sound — a claim
can be wrong. **This corpus never makes one wrong**, so the argument is
untested here.

**The methodological error, stated plainly:** the only baseline run was the
frozen engine, which this project had already published a three-defect report
about. It was *guaranteed* to look bad. A benchmark needs a **dumber** baseline
as well as a worse one, and the ten minutes that would have caught this were
never spent. `corpus/leakage_audit.py` is 1,346 lines asking *"does a trivial
predicate identify this planted class?"* It never asks *"does a trivial
predicate solve the task?"* — the same error class it was built to find, one
coordinate up.

### 0.2 Contract §6.3 stated a theorem, gated on it, and the theorem is false

§6.3 claimed that at 0% attestation coverage no composition claim exists, so
`|Verified| = 0` necessarily. Oracle gate **G5** enforced it.

Measured on `corpus/datasets/A20_B0_Cmax/`: **12 of 12** `settlement_report.csv`
rows present with a `settlement_id`; **12 of 12** reported amounts matching a
bank credit verbatim; **255 of 314** recon rows carrying `settlement_id`.

A composition claim exists, it entails a checkable prediction about the bank's
amount, and the prediction can be tested — which is exactly §3.3's definition of
`Verified`. **G5 would have rejected correct answers as contract violations.**

§6.3 and G5 are now **withdrawn and dated**, with the original text left
visible. §6.4's `ReconstructibleInstance` amendment is **retained** — its own
justification stands independently — but it was reached through this
misdiagnosis, and that is recorded rather than left to look prescient.

This is the sharpest failure in the phase. `RESOLVER_CONTRACT.md` §0 names the
defect it exists to prevent: *"a claim was made that no evidence supported, and
the type system had no way to notice."* §6.3 asserted a claim a priori,
described it as *"stated in advance, as a prediction of the contract"*, and
gated on it without measuring it. **The document written to prevent that error
committed it.**

---

## 1. What this phase was for

The previous engine reported **96.55% match rate and 1.000 precision** on the
frozen primary dataset, then produced **50 confident wrong answers** on held-out
data. Root-cause analysis found three engine defects. An audit of the *data*
found seven more — and the data defects matter more, because they mean the
primary dataset was **structurally incapable** of exposing the engine defects.

So this phase did not build a better engine. It built the apparatus that can
tell whether any engine is lying:

- a **resolver contract** that makes an unsupported claim unrepresentable,
- a **benchmark corpus** of 14 datasets spanning the regime where the problem
  actually becomes hard,
- a **leak audit** that searches for shortcuts rather than checking a list,
- an **oracle** whose gates cannot all be passed by answering nothing,
- a **baseline run** of the old engine against all of it.

Whether that was the right thing to build with the time available is argued in
§9, including the case against.

---

## 2. Timeline, and why the ordering is the evidence

`git log`, verbatim. The ordering is not incidental — it is the whole integrity
argument, and it is checkable by anyone.

| when | commit | what |
|---|---|---|
| 2026-08-23 14:37 | `65c1ce2` | defect investigation: 3 engine defects, 2 in the primary set |
| 2026-08-23 15:25 | `a110212` | **resolver contract** — before any corpus data existed |
| 2026-08-24 00:55 | `589c446` | **corpus seeds** — before any data was generated |
| 2026-08-24 02:15 | `0000ad0` | **baseline prediction** — before the old engine was run once |
| 2026-08-24 02:25 | `9c441d9` | leak audit, oracle, spec, decisions 20–30 |
| 2026-08-24 14:17 | `5460752` | 14 datasets + baseline results + decisions 31–32 |

Contract → seeds → data → prediction → results. A corpus built after the
contract cannot be shaped to an implementation; a prediction committed before
the run cannot be edited to match it. This is the protocol `DECISIONS.md` §17
established for the held-out seed, applied to the whole phase.

**Between 02:25 and 14:17 the corpus was regenerated five times**, because its
own leak audit rejected it four times. That is §7.

---

## 3. What exists now

| artefact | lines | what it is |
|---|---:|---|
| `resolver_contract/types.py` | 1,064 | the outcome vocabulary, executable. No algorithm. |
| `resolver_contract/RESOLVER_CONTRACT.md` | 508 | the prose, with rejected alternatives |
| `corpus/generator/` | 2,555 | parameterised, seeded, deterministic dataset family |
| `corpus/leakage_audit.py` | 1,346 | five-family leak search + class efficacy |
| `corpus/oracle.py` | 554 | scores `(resolver_output, ground_truth)` only |
| `corpus/baseline_old_engine.py` | 212 | runs the frozen cascade over the corpus |
| `corpus/CORPUS_SPEC.md` | 465 | axes, what each detects, named gaps |
| `corpus/BASELINE_OLD_ENGINE.md` | 289 | prediction, then results |
| `corpus/tests/` | 751 | 182 tests |
| `corpus/datasets/` | 7.4 MB | 14 datasets, each with key, hashes, report |
| `DECISIONS.md` | 32 entries | each with its rejected alternatives |

**487 tests pass** (182 new + 305 pre-existing). Frozen dataset hashes verify
6/6. `git status` on `engine/` and `matching/` is empty — nothing under the
frozen list was modified.

---

## 4. The measurements that matter

### 4.1 The ten defects in the frozen dataset — all re-verified today

| # | defect | measurement, re-derived |
|---|---|---|
| D1 | `Determinate` means "unique among max-applied-debits subsets" | 2 primary credits had 3 closing subsets each, reported `Determinate` |
| D2 | consumption on uncorroborated `Determinate` | 0 on primary (unreachable), **50 rows** on held-out |
| D3 | `Ambiguous.certain_rows` assigns rows | 3 wrong placements survive the best single fix |
| D4 | bank statement re-encodes the attestation | `utr == str(settled_at)+settlement_id[-6:]` on **11/11** batches; narration embeds it **9/12**; posting lag **0 days**, always |
| D5 | calibration rows are greppable | **6 rows minted** (3 adjustments, 3 refunds). `description == 'Settlement processing fee'` → precision **1.000**, recall **1.000** |
| D6 | orphan ERP invoices are sortable | the **6 highest invoice numbers** are exactly the 6 orphans; file positions 45, 65, 74, 102, 143, 161 of 184 |
| D7 | the decoy class exercises nothing | credit deltas **−8,711 / −3,670 / 0 / +11,732** — 1 of 4 collides, beside **4** incidental collisions |
| D8 | `source_ref` is still a class marker | `'recon sample adj_EhcHONhX4ChgNC shape'` → `c09`, precision **1.000**, recall **1.000** |
| D9 | the GST leg has no reconciliation work | 20-row file; 3 ITC findings, each a single-column filter at precision 1.000 |
| D10 | bank statement is a bijection with the batch list | 12 lines / 12 batches / 12 distinct dates / all Wednesdays / lag 0 |

Max pool size in the frozen set: **26**. Closure uniqueness collapses above
~30. The dataset sits entirely below the regime where the problem is hard.

### 4.2 The corpus

**6,106 recon rows · 280 bank lines · 4,942 ERP invoices · 322 GSTR-2B lines**
across 14 datasets. **112 foreign bank lines** (credits, debits, reversals) and
**13 planted wrong attestations** — neither shape exists in the frozen set at
all.

Ground truth records **88 determined instances** (unique complete closure,
attested, attestation correct) and **31 reconstructible instances** (unique
complete closure, cross-line exclusive, unattested).

### 4.3 The single most important measurement: closure collapses with pool size

Closure counted with **no objective**, cap 500 — the register the frozen key
could not produce, because it enumerated only subsets tying at the maximum.

| pool | unique closure | median *k* | max *k* | determined | old engine `Determinate` | old engine abstained |
|---:|---:|---:|---:|---:|---:|---:|
| 10.2 | 12/12 | 1 | 1 | 11 | 12/20 | 0/11 |
| 19.0 | 11/12 | 1 | 58 | 10 | 6/20 | 5/10 |
| 28.6 | 10/12 | 1 | 500 | 9 | 4/20 | 6/9 |
| 34.8 | **5/12** | 4 | 437 | 5 | 1/20 | 4/5 |
| 51.8 | **3/12** | 13 | 72 | 3 | 1/20 | 2/3 |

This independently reproduces `investigation/DEFECT_REPORT.md` §2 on new data,
and it is the axis the frozen set could not test.

### 4.4 Attestation coverage

| coverage | determined | reconstructible | engine abstained | unrepresentable claims |
|---:|---:|---:|---:|---:|
| 100% | 10 | 1 | 5/10 | 5 |
| 75% | 8 | 4 | 5/8 | 6 |
| 50% | 4 | 7 | 3/4 | 9 |
| **0%** | **0** | **11** | 0/0 | 4 |

The 0% row is why the contract needed amending — see §5.

### 4.5 Every dataset, every number

| dataset | seed | pool | cov | rule | rows | unique closure | med k | max k | det | recon | D | A | U | wrong | abstained | unrep |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `A10_B100_Cmax` | 20260825 | 10.17 | 1 | max_under_cap | 173 | 12/12 | 1 | 1 | 11 | 1 | 12 | 0 | 8 | 0 | 0/11 | 0 |
| `A20_B0_Cmax` | 20260831 | 19.0 | 0 | max_under_cap | 314 | 11/12 | 1 | 6 | 0 | 11 | 3 | 11 | 6 | 0 | 0/0 | 4 |
| `A20_B100_Cfifo` | 20260902 | 18.25 | 1 | fifo_under_cap | 314 | 11/12 | 1 | 36 | 10 | 1 | 4 | 8 | 8 | 0 | 6/10 | 4 |
| `A20_B100_Cmax` | 20260824 | 19.0 | 1 | max_under_cap | 314 | 11/12 | 1 | 58 | 10 | 1 | 6 | 6 | 8 | 0 | 5/10 | 5 |
| `A20_B100_Crandom` | 20260903 | 20.0 | 1 | random_valid | 314 | 10/12 | 1 | 2 | 9 | 1 | 3 | 7 | 10 | 0 | 7/9 | 4 |
| `A20_B100_Crandom0` | 20260906 | 24.5 | 1 | random_valid | 314 | 6/12 | 2 | 100 | 6 | 0 | 4 | 8 | 8 | 0 | 2/6 | 3 |
| `A20_B50_Cmax` | 20260830 | 18.92 | 1/2 | max_under_cap | 314 | 11/12 | 1 | 15 | 4 | 7 | 6 | 6 | 8 | 0 | 3/4 | 9 |
| `A20_B75_Cmax` | 20260829 | 18.58 | 3/4 | max_under_cap | 314 | 12/12 | 1 | 1 | 8 | 4 | 4 | 9 | 7 | 0 | 5/8 | 6 |
| `A30_B100_Cmax` | 20260826 | 28.58 | 1 | max_under_cap | 455 | 10/12 | 1 | 500 | 9 | 1 | 4 | 7 | 9 | 0 | 6/9 | 4 |
| `A40_B100_Cfifo` | 20260904 | 35.33 | 1 | fifo_under_cap | 599 | 7/12 | 1 | 33 | 6 | 1 | 5 | 7 | 8 | 0 | 3/6 | 3 |
| `A40_B100_Cmax` | 20260827 | 34.83 | 1 | max_under_cap | 599 | 5/12 | 4 | 437 | 5 | 0 | 1 | 14 | 5 | 0 | 4/5 | 5 |
| `A40_B100_Crandom` | 20260905 | 35.0 | 1 | random_valid | 599 | 8/12 | 1 | 57 | 7 | 1 | 2 | 9 | 9 | 0 | 6/7 | 1 |
| `A40_B50_Cmax` | 20260901 | 35.5 | 1/2 | max_under_cap | 599 | 2/12 | 4 | 76 | 0 | 2 | 2 | 12 | 6 | 0 | 0/0 | 5 |
| `A60_B100_Cmax` | 20260828 | 51.83 | 1 | max_under_cap | 884 | 3/12 | 13 | 72 | 3 | 0 | 1 | 8 | 11 | 0 | 2/3 | 3 |

### 4.6 The baseline: the frozen engine over all 14 datasets

280 bank lines. **`Determinate` 57 · `Ambiguous` 112 · `Unresolved` 111.**

| quantity | measured |
|---|---:|
| confident wrong answers | **0** |
| foreign bank lines adopted | **1 of 112** |
| rows misplaced | 10 |
| **abstained on determined instances** | **49 of 88 (55.7%)** |
| unrepresentable claims | **56** |
| `AttestationDiscrepancy` detected | **0 of 13 planted** |
| non-answer share, pool 10 → 52 | **40% → 95%** |

Unrepresentable claims, 55 of 56 categorised (the per-dataset detail list caps
at 8 and one dataset had 9): **45 `certain_rows` assignments**, 9 `Determinate`
on unattested lines, 1 `Determinate` on a foreign line.

---

## 5. The contract amendment, and the theorem it rested on

`ReconstructibleInstance` and gate **G8** were added **2026-08-24, after
generation began**. It is dated in `RESOLVER_CONTRACT.md` §6.4 and
`DECISIONS.md` §31 rather than folded into the original text.

**Why it was necessary.** At 0% attestation coverage every gate was vacuous:
§6.3's theorem forces `|Verified| = 0`, so the soundness gates had nothing to
range over, and `DeterminedInstance` requires an attestation, so the abstention
gate had an **empty subpopulation** — while **11 bank lines** had unique,
complete, objective-free closure. A resolver answering nothing scored perfectly
on the one axis point that is purely about reconstruction.

**The theorem is what disguised it.** §6.3 predicted the cell would be empty;
the prediction came true, and nothing was learned. Stating a theorem and then
not checking what it leaves *unmeasured* is its own failure mode.

**No dataset was regenerated for it** — G8 is derived from closure registers
already in every key. That is what keeps it an addition rather than a re-cut of
the benchmark after seeing results.

**But the diagnosis was wrong** (§0.2). The B0 cell is *not* purely about
reconstruction: the attestation is present there in both artefacts, and
`Verified` is achievable. `ReconstructibleInstance` and G8 are **retained**,
because a line with unique, complete, cross-line-exclusive closure and no usable
bank reference genuinely is reconstructible and abstaining on it genuinely is a
defect. The reasoning that produced them was not. §6.3 and G5 are withdrawn.

---

## 6. Accuracy audit — five errors in this project's own documents

The instruction for this checkpoint was accuracy above everything. Re-deriving
every number found **three claims this project had published that were wrong**.
All three are now corrected in place, and recorded here because a document that
catalogues other people's unverified claims has no standing to carry its own.

### 6.1 D5 — the `amount` column claim was wrong, twice

Published: *"the `amount` column alone separates them — 4 minted debits at
1,200,573–3,295,351 paise against every organic adjustment at 3,195–39,197."*

Measured today:

- the planters minted **3 adjustments**, not 4 — at 1,856,136 / 2,117,064 /
  3,295,351 paise. The **1,200,573** "Chargeback recovery - bulk" row that
  earlier drafts counted as minted is **organic**;
- `amount ≥ 1,856,136` alone reaches precision **0.750**, not 1.000, because a
  genuine chargeback debit of **1,939,019** sits inside the range;
- the perfect separators are `description == 'Settlement processing fee'` and
  the **pair** `amount ≥ 1,856,136 AND dispute_id IS NULL`, both precision
  1.000, recall 1.000.

The defect is real and the fix is unchanged. The overstatement was not. If
anything the corrected version motivates the design better: the leak needed a
column **pair** to find, which is exactly why the audit searches pairs.

### 6.2 Planted wrong attestations: 13, not 14

One axis point had no attested batch with ≥3 credit rows to corrupt and
correctly recorded `planted: false` with that reason. The `0 of 14` in an
earlier draft of the baseline report is now `0 of 13`.

### 6.3 The unrepresentable breakdown is a capped sample

`45 / 9 / 1` sums to 55, against a true total of **56**. The per-dataset
`detail` list caps at 8 entries and one dataset had 9. Stated as "55 of 56
categorised" rather than presented as exact.

### 6.4 A wording error

`DECISIONS.md` §32's heading said the corpus was *"regenerated three times"*
and then documented four rounds of findings across five generations. Corrected
to "regenerated five times, because its own audit failed it four".

### 6.6 A sixth: the resolver called an enumeration COMPLETE when it was not

**Found by the oracle, in the resolver written to prevent this defect class.**
`resolver/enumerate_closures.py` computed `complete` from an externally
measured clock rather than from CP-SAT's own status, so a search that stopped
on the solver's internal limit at 9.98 s of a 10 s budget was recorded as
exhaustive. Measured at `corpus/datasets/A40_Bnone_Cmax` bank[7] under CPU
load: **194 subsets returned `complete=True` with the truth not among them**;
run alone the same line correctly reports 200 / `cap_reached`. Fixed to
`complete = (status == OPTIMAL)`, one line. Both oracle runs are published
(`corpus/ORACLE_RESULTS_RUN1.md` and the appendix to
`corpus/THREE_SYSTEMS.md`): 5 falsely-exhaustive enumerations went to 0, no
`Verified` and no `Reconstructed` changed, and 8 `Ambiguous` became
`Unresolved(enumeration_truncated)` — the weaker and true statement.
`DECISIONS.md` §39 names what else it could have affected silently. It is the
same shape as `Determinate` meaning "unique among maximising subsets" and as
withdrawn §6.3 asserting an unmeasured theorem, and it was written by someone
who had just catalogued both.

### 6.5 What re-derivation confirmed unchanged

An independent recomputation of every cell of `BASELINE_OLD_ENGINE.md` Part 2
against `corpus/baseline_results.json` found **the 14-row table exact** — every
pool mean, outcome count, wrong, foreign-adopted, abstained, unrepresentable and
mean-*k* figure — and confirmed the derived prose claims (the 40%→95% collapse,
the 25%/55% `Unresolved` shares, the 4.5–24.1 *k* range). One dataset was
re-run from a cold process and reproduced byte-identically.

Also unchanged:
D4 (11/11, 9/12, lag 0), D6 (top-6 invoice ordinals, positions 45–161 of 184),
D7 (deltas −8,711 / −3,670 / 0 / +11,732), D8 (precision 1.000, recall 1.000),
D9 (20 rows, 3 single-column findings), D10 (12/12/12, all Wednesdays), max
pool 26, and every figure in §4.3–§4.6 above.

---

## 7. The audit found more in this corpus than in the frozen one

Rediscovering D4–D7 shows the audit is *sensitive*. Finding **unknown** problems
is what it is for. Across five regeneration rounds it found **four real leaks I
introduced** plus **three flaws in its own statistics** — in a corpus built
specifically to avoid leaks, by someone who had just catalogued seven.

| round | finding | visible to inspection? |
|---|---|---|
| 1 | orphan ERP invoices had a blank `order_id` → precision 1.000, recall 1.000 | maybe |
| 2 | `narration CONTAINS 'clo'` → foreign lines at precision 1.000 | no |
| 3a | class scored at row level when the fact is settlement-level; p-value treated ~69 clustered rows as independent | no |
| 3b | at 0% coverage `settled == True` reaches precision 1.000 at lift **1.2×** — the definition of the axis point, not a leak | no |
| 4 | `RZPX…` reference prefix separated unattested settlements | maybe |
| 5 | **correct format, wrong distribution** — uniform 0–999999 against the bank's narrow counter, settlement date against posting date. Values sorted into two bands, precision 1.000 | **no** |
| 5b | class of 3 in 12: even a *perfect* separator could only reach p = 4.5×10⁻³, above alpha — not certifiable clean **or** leaking | no |

**Round 5 is the finding worth keeping.** Matching a field's *format* is not
enough. If the distribution differs, **the distribution is the marker**. No
reviewer reading the generator would have caught that a correctly-formatted
reference sorts into a separate band.

**Round 5b forced a real statistical rule.** Two findings looked identical — a
precision-1.000 separator on a small class — and needed opposite verdicts:

| case | class | min attainable *p* | verdict |
|---|---|---:|---|
| frozen D5 | 6 rows in 240 | 4×10⁻¹² | **powered** → real leak, gate it |
| corpus d04 | 3 settlements in 12 | 4.5×10⁻³ | **underpowered** → noise, report only |

No single precision threshold does both jobs, so the audit reports statistical
power explicitly instead of pretending a verdict exists.

**Final state: 14/14 datasets pass their own audit.** The frozen-set validation
still rediscovers D4, D5, D6 and D7 unaided.

---

## 8. Impressive and disappointing

### 8.1 The most impressive

**Caveat first:** §0.1 means the abstention finding is measured against a bar a
`GROUP BY` clears. It remains true and it remains the best *diagnostic* result
in the phase, but it is no longer the strongest claim available.

**The abstention finding.** The frozen engine produced **0 confident wrong
answers** across 14 datasets and abstained on **49 of 88** lines that provably
have exactly one answer. Read the first number alone and it looks sound. It did
not avoid wrong answers by being right — it avoided them by declining, on 56% of
solvable instances.

**An oracle with only soundness gates would have scored that run perfectly.**
That is the entire argument for gating abstention, demonstrated rather than
asserted, and `corpus/tests/test_oracle.py` proves it mechanically: a resolver
that returns `Unresolved` to everything trips **G7/G8 and nothing else**.

**The strongest claim that survives §0 intact: `settlement_utr ==
str(settled_at) + settlement_id[-6:]` on 11 of 11 batches**, with the narration
embedding it on 9 of 12 and posting lag 0 days always. That is a real defect in
real-shaped data, measured, and every recon vendor has some version of it. It
does not depend on any corpus design choice.

**Runner-up: 56 unrepresentable claims against 0 wrong answers**, 45 of them via
`certain_rows`. D3 is not an edge case in that engine — it is its *main*
assignment path once ambiguity dominates. The defect is not that the answers are
wrong; it is that most confident ones are claims nothing in the record supports,
**including the correct ones**.

### 8.2 The most disappointing

**The corpus was never run against a trivial baseline** (§0.1). This is the
most disappointing thing in the phase and it displaces everything below it.
1,346 lines of leak audit, five families, KS tests, Bonferroni correction, four
regeneration rounds — and the ten-minute check that the task is not solvable by
one `GROUP BY` was never run. The rigour is real, deep, and pointed one
coordinate away from the thing that undermines it.

**Second: a theorem was asserted and gated without being measured** (§0.2), and
a dated amendment was built on top of the misdiagnosis.

**There is no resolver.** This is the honest headline of the disappointing
column, and no amount of apparatus quality changes it. The submission's only
working reconciliation engine is the frozen one with three known defects.

**The foreign-credit class fires 1 time in 112.** It proves the guard is missing
without ever exercising it. Foreign amounts are drawn independently of the
ledger, and a subset of a 20–50 row pool almost never nets to a target no
process generated. As built, it tests almost nothing. My prediction said 30–70%.

**The premise-sharing statistic cannot be computed against the only engine
available.** Contract §6.2 needs a rank-1 candidate; the frozen cascade filters
before enumerating — which *is* the defect — so it never exposes one. Axis C
falls back to an outcome-level proxy that is degenerate when the wrong-answer
rate is 0 everywhere. The statistic is sound for a resolver that obeys the
contract and blind to one that does not.

**D9 stands, essentially untouched.** All four axes are settlement-side. The GST
leg went from 20 rows to ~23 per dataset and stopped `itc_availability` being a
perfect proxy, but there is still no volume of ITC decisions, no
partially-filed-supplier population, no IRN timing distribution. **Any GST claim
in a headline remains substantially unearned.**

**No wrong-*bank*-side class.** The corpus plants an attestation that is wrong
but never a case where the two sources contradict and truth is on the **bank**
side. So "two independent sources agree" is never tested at the one point where
the direction of disagreement matters.

**14 of 60 grid cells.** B × C is untested entirely.

---

## 9. Is this a worthy hackathon submission? The argument, both sides

### The case against — and it is strong

A judge has five minutes. The deliverable is a **measurement apparatus**, not a
product. Nothing here reconciles a merchant's books better than what existed
yesterday; the one engine in the repo abstains on 56% of solvable lines. The
uncomfortable reading is available and a sharp judge will reach for it:
*"this team could not fix the engine, so they built an elaborate argument for
why the engine cannot be fixed, and called the failure rigour."*

The abstention result is presented as a **finding**. It is equally describable as
the engine failing at its job, with the submission choosing the flattering frame.
That the abstention gate exists *because* I anticipated the loophole is a good
answer — but it is an answer that has to be given, and it will be asked.

### The case for

The 96.55% → 50-wrong-answers sequence is the entire reason this phase exists.
Reporting a match rate on a dataset that cannot expose your defects is not a
small methodological wobble — it is the failure mode of most reconciliation
demos, including the one this repo shipped a day earlier. The corpus makes that
class of error *impossible to hide*, and it did so on real, measured evidence:
five leaks in its own data, three wrong claims in its own documents, one
contract hole that a theorem had disguised.

For a **payments company**, "we can prove our engine is not lying" is not a
consolation prize. It is the thing you cannot buy and the thing that actually
gates production deployment.

### Verdict

**Revised after §0. This does not win as it stands, and in a panel round it
would cost the offer.**

Not because "measurement apparatus" is a weak story — it is a strong one, and
the evidence discipline behind it is unusual and mechanically checkable: commit
ordering visible in `git log`, frozen hashes, an audit validated against known
defects, an oracle validated against a known-bad resolver, two predictions
recorded as WRONG, and a public record of five of its own errors.

It does not win because **the apparatus does not currently measure what it
claims**. A judge who misses §0.1 is unimpressed by a repo with no product. A
judge who *finds* it concludes the team built an elaborate epistemology on a
benchmark whose central difficulty is self-imposed, and never sanity-checked it
against a baseline dumber than the one it attacked. That is a first-week
omission wearing a philosophy degree, and it is fair.

The distance to a genuinely strong submission is small and specific — §10 —
because everything needed to close it already exists. The corpus, the contract,
the oracle and the audit are all sound *machinery*. What is missing is one
planted class that makes the PSP's claim falsifiable, and one resolver that the
oracle actually scores.

---

## 10. What would convert it, prioritised

**0. Disclose §0.1 as the corpus's most important finding about itself.**
`corpus/baseline_naive.py` now exists and is committed. Converting a fatal
discovery into an honest headline is worth more than any feature here, and it
is already done — what remains is putting it in `CORPUS_SPEC.md` §8 and the
README in the same words used above. *Done as part of this checkpoint.*

**0b. Plant one WRONG `settlement_id` per dataset.** The single highest-value
change to the corpus. One batch whose attestation names rows that are not its
true composition, where the arithmetic still closes. This is the case where the
naive resolver breaks, where `AttestationDiscrepancy` becomes reachable for a
non-trivial reason, and where withholding the attestation finally earns its
keep. **Without it the corpus cannot falsify the premise it is built on.**

**1. Build the minimum sound resolver, and let the corpus judge it.** It does not need to be clever — attestation + closure
consequence check → `Verified`; unique unfiltered closure + cross-line
exclusivity → `Reconstructed`; everything else declines with a reason. Run the
oracle. Publish the six-way accounting beside the old engine's. Even a modest
score turns *"here is a ruler"* into *"here is a ruler, and here is the thing it
built."* Without this the submission has no product.

**2. Make the foreign-credit class actually fire.** Draw foreign amounts that
*are* reachable from the pool. This converts a 1/112 curiosity into a real test
of "is this credit even ours?" — a question the frozen set cannot ask and every
payments engineer will.

**3. Expose a rank-1 candidate in the new resolver** so axis C's premise-sharing
statistic can finally be computed. It is the only falsifiable form of the test
and currently it has never run.

**4. Add one wrong-bank-side class.** A bank splitting one settlement into two
credits. Cheap, and it closes the largest named gap in the contract's
independence story.

**5. Either earn the GST claims or cut them.** A fifth axis, or delete the GST
leg from the headline and say why in one line. Shipping an unearned claim to a
payments company is the single most expensive mistake available.

**6. Rewrite `README.md`.** It is currently a 223-line internal strategy memo
("Council Conclusion") that profiles the hiring process, credits eight
subagents, and still advertises a `95.4% auto-matched` figure this repo spent
three commits proving was luck. The word "corpus" appears once. It is the first
thing a judge opens and it contradicts the work behind it.

**Cut if time runs out:** the remaining grid cells, the φ=0 axis point, the
wrong-bank-side class (name it, do not build it), the premise-sharing statistic
(unmeasurable, and after §0.1 not the most interesting question), and any
further leak-audit refinement.

---

## 11. Standing gaps, stated plainly

- **the corpus is solvable by a `GROUP BY`** (§0.1) — no false `settlement_id`
  is ever planted, so the premise the architecture rests on is never falsified
- **contract §6.3 and oracle gate G5 are withdrawn** (§0.2)
- no resolver exists (deliberate, and now the critical path)
- the foreign-credit class is a rare-event class as built (1/112)
- premise-sharing is uncomputable against a filter-before-enumerate engine
- D9: the GST leg still has no real reconciliation work
- no wrong-bank-side class
- 14 of 60 grid cells; B × C untested
- `Reconstructed`'s cross-line exclusivity is necessary, not sufficient — a
  credit outside the window cannot be excluded against
- the baseline measured G7 abstention (49/88) but **not** G8 abstention over the
  31 reconstructible instances; that run was not repeated
- two implementations of one spec exist (`corpus/generator/sim.py` vs the frozen
  simulator), held together by a differential test rather than by construction

---

## 12. The resolver phase — what shipped, and what it measures

**Written 2026-08-25.** §§0–11 above describe the corpus phase and stand
unchanged except for §6.6. This section is what happened after it, and it
closes §0.1.

### 12.1 What was built

| artefact | what it is |
|---|---|
| `corpus/datasets/A20_Bnone_Cmax`, `A40_Bnone_Cmax` | the PSP artefact is **absent** — no settlement columns at all, no settlement report. Seeds committed before the data existed. |
| `corpus/datasets_v2/` (14) | the same axis points at new seeds, each with **one false `settlement_id`**: a restatement whose arithmetic still closes. The original fourteen were not regenerated. |
| `corpus/triviality_check.py` | *does a trivial predicate SOLVE the task?* — the question the leak audit never asked, now permanent output on every dataset |
| `resolver/` | the resolver. Three tiers, hard isolation from the answer key, rank-1 exposed on every candidate set. |
| `corpus/score_resolver.py`, `corpus/three_systems.py`, `run_all.py` | the oracle run and the comparison, one command |

**Ordering, all in `git log`:** contract → corpus seeds → corpus → baseline
prediction → baseline → **new seeds → absence + v2 data → resolver → oracle**.
The resolver was committed before the oracle scored it once.

### 12.2 §0.1 is closed, and the answer is not flattering

`corpus/triviality_check.py` over all 30 datasets: **15 `TRIVIAL`, 13
`PARTIAL`, 2 `N/A`.** The original fourteen are all `TRIVIAL` and stay that
way — that is now their labelled role as the easy regression baseline rather
than an unexamined assumption.

**On the original fourteen the naive `GROUP BY` still wins outright** — 168/168
compositions, 0 wrong, 0 abstentions — and `corpus/THREE_SYSTEMS.md` states
that before it states anything else. What changed is that there are now two
families where it does not:

| | naive `GROUP BY` | frozen cascade | new resolver |
|---|---|---|---|
| original 14 | **168/168, 0 wrong** | 55/56, 1 wrong, abstained 50/88 | 143/144, 1 wrong, abstained 0/88 |
| PSP absent (2) | **cannot run** | **cannot run** (`KeyError: 'settlement_id'`) | 1/1, 0 wrong, abstained 15/18 reconstructible |
| false attestation (14) | 154/167, **13 wrong** | 48/50, 2 wrong, abstained 42/76 | **132/132, 0 wrong**, 24/26 discrepancies found |

### 12.3 The oracle, over 30 datasets

**Zero on G1, G2, G4, G6 and G7.** No wrong `Verified`, no `Verified` without
two independent parties, no assignment without a warrant, no provenance the
corpus contradicts, and — the one that matters against the old engine — **no
abstention on any of the 164 determined instances**, against the frozen
cascade's 92 of 164.

**28 of 30 datasets PASS. The two failures are both PSP-absence points**, on
G8 (15 of 18 reconstructible lines declined) and G3 (the truth is not inside
the candidate sets it built).

### 12.4 The finding, and it is a real tension in the contract

The absence failure is structural, and it was written down in
`DECISIONS.md` §33 and `CORPUS_SPEC.md` §6.5 **before the run**:

> Contract §2.4 permits only `Verified` to consume rows. `Verified` needs an
> attestation. Where the attestation is absent, nothing ever consumes, so the
> eligible pool grows monotonically — measured on `A20_Bnone_Cmax`, from **8
> rows at the first credit to 265 at the last** — and closure stops being
> unique long before the window ends.

So the rule that prevents defect D2 (a contested line spending the pool and
starving the next one) is the same rule that makes reconstruction infeasible
in the one cell where reconstruction is all there is. **Both directions are
correct in isolation and they conflict.** The resolution is a joint formulation
over the whole window rather than a line-at-a-time pass with a consumption
rule — which `DECISIONS.md` §2 already measured as returning UNKNOWN at 60 s on
1,347 booleans.

This is named here and **not fixed**, because the standing instruction for this
phase was that discovering a foundational problem is answered by documenting it
and shipping, not by building the next layer of apparatus. It is the single
most interesting open problem the repository now contains.

### 12.5 Standing gaps, updated

Superseded from §11: *"the corpus is solvable by a `GROUP BY`"* — now measured
per dataset and labelled, with two families that resist it. *"No resolver
exists"* — one does, and it is scored.

Still standing, unchanged: contract §6.3 and gate G5 withdrawn; the
foreign-credit class fires 1 in 240; D9, so **any GST claim remains
unearned**; no wrong-*bank*-side class; 14 of 60 grid cells and B × C untested;
`Reconstructed`'s cross-line exclusivity necessary but not sufficient; two
implementations of one spec held together by a differential test.

New, from this phase:

- **the consumption/reconstruction conflict** above;
- **the premise-sharing statistic still cannot be computed** — exactly **1**
  qualifying instance across 30 datasets. The frozen cascade could not supply
  one because it filters before enumerating; this resolver ranks everything it
  enumerates but rarely needs to enumerate, because the attestation resolves
  the line first. Same unmeasurable, a different reason;
- **`AttestationDiscrepancy` and `Reconstructed` are mutually exclusive per
  line**, so on a falsely attested line the resolver reports the finding and
  forgoes a reachable answer. The vocabulary cannot say *"the record is wrong
  AND here is what actually happened"*;
- **the undetectable false attestation is named, not planted** — see
  `DECISIONS.md` §34 for why, including the reading it invites;
- **238 of 275 `Verified` are non-decisive**, and the oracle's
  `AttestationDiscrepancy` precision metric counts a true reversal finding as a
  false one because its numerator is *planted wrong attestations*. Both are
  reported in `corpus/THREE_SYSTEMS.md` under *"What the new resolver gets
  wrong"*.
