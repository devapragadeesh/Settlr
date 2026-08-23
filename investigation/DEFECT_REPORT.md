# DEFECT REPORT — confident wrong answers in Stage 3

**Status: three defects, not one. Two of them are present in the PRIMARY set
and were not caused by reversals.** Diagnosis only; `matching/`, `engine/data/`,
`engine/ground_truth/`, `simulator.py` and `generator.py` are unmodified.

Every claim below is a measurement over the data. Reproduce with
`investigation/dump_traces.py`, `investigation/sweep.py`,
`investigation/run_remediation.py`.

---

## 0. Headline — it is worse than the held-out run indicated

The held-out report attributed all 50 errors to one unseen class and showed
"0 rows placed incorrectly" on the primary set. Both statements are true and
both are misleading about the engine's soundness.

| finding | severity |
|---|---|
| **D1.** `Determinate` is granted when the *max-applied-debits optimum* is unique, **not** when closure is unique. On the primary set **2 of 12 bank credits had 3 closing subsets each and were reported `Determinate`**. The engine's 1.000 precision there is luck, not proof. | **critical — unsound guarantee, primary set affected** |
| **D2.** A `Determinate` resolution on a bank line the attestation does not corroborate **consumes** pool rows. This is the 50-row failure. The branch **never executes on the primary set** — every primary bank line is attested — so the dataset could not have exposed it. | **critical — caused the 50 wrong rows** |
| **D3.** `Ambiguous.certain_rows` assigns rows with no corroboration either. It is a **third** confident-assignment path that any `Determinate`-only guard misses; it produced 3 wrong placements that survive the best single fix. | **high — unguarded path** |

**D1 can produce actively wrong answers with no reversal present.** Minimal
case `adjustment_exactly_offsets_a_payment`, 3 rows, 1 bank line:

```
bank credit 400000, pool = {pay_O1 +400000, pay_O2 +150000, adj_O1 -150000}
closing subsets (independent enumeration, no objective):
    ('pay_O1',)                        debits_applied = 0   <- TRUTH
    ('adj_O1','pay_O1','pay_O2')       debits_applied = 1   <- ENGINE CHOSE
engine result: Determinate, 2 false positives, full confidence
```

The engine's objective **maximises applied debits**, so it actively *preferred*
the wrong subset. Two rows that settle nowhere were placed into a batch with a
closing balance proof.

---

## 1. Defect boundary — the 50 rows (Task 1)

Full table: `investigation/task1_per_row.md` (50 rows, individually determined).

| bank line taking the rows | rows | true settlement | true line | (b) closure | (c) true decomp also closing? | (d) why unreachable |
|---|---:|---|---|---|---|---|
| `bank[3]` utr `…osmYw6` | 7 | `setl_b62bWG…0n3xCG` | `bank[5]` | **exact, residual 0** | **NO** — 1 closing subset, `OPTIMAL`, not truncated | prior consumption by `bank[3]` |
| `bank[7]` utr `…GqaPVy` | 22 | `setl_J977hu…FQuOA5` | `bank[9]` | **exact, residual 0** | **NO** — 1 closing subset, `OPTIMAL`, not truncated | prior consumption by `bank[7]` |
| `bank[12]` utr `…LGOvuF` | 21 | `setl_jS5VGy…3XVRBM` | `bank[14]` | **exact, residual 0** | **NO** — 1 closing subset, `OPTIMAL`, not truncated | prior consumption by `bank[12]` |

**(c) is NO for all 50 rows, established individually.** This was **not** an
undetected ambiguity. At each credit-A line the pool admitted exactly one
closing subset — the enumeration did not miss a tie, because there was no tie
to miss. **The ambiguity machinery is not implicated in the 50-row failure.**

**(d) is prior consumption for 50 of 50.** At the true line's turn, **0 of the
true rows remained in the pool** in all three cases.

**What the engine actually did**: the decomposition it assigned to credit A is
**byte-identical to the true composition of credit B**. It found the right rows
and bound them to the wrong bank line — an *identity* error, not an arithmetic
or subset-selection error.

---

## 2. Under-determination, measured directly (Task 2)

Independent enumeration (no objective, cap 500) over every bank credit in both
sets.

**Closure uniqueness collapses with pool size** — engine's own pools:

| pool size | credits | with >1 closing subset | median closing count |
|---|---:|---:|---:|
| 0–10 | 2 | 0 (0%) | 1 |
| 11–20 | 9 | 2 (22%) | 1 |
| 21–25 | 10 | 4 (40%) | 1 |
| 26–30 | 4 | 3 (**75%**) | 7 |
| 31–40 | 2 | 2 (**100%**) | 104 |

Over **unconsumed** pools (the problem's true under-determination), every pool
above 30 rows had multiple closing subsets — median 73–175, up to the 500 cap.

### Direct answer: primary credits with >1 closing subset NOT flagged ambiguous

**Two.** `bank[1]` (pool 23, **3** closing subsets) and `bank[8]` (pool 25,
**3** closing subsets), both reported `Determinate`.

**Why not flagged:** `enumerate_decompositions` maximises applied debits, then
enumerates *only solutions achieving that optimum*. In both cases the engine's
subset applies strictly more debits than every rival, so the optimum is unique
and `resolve_from_candidates` sees a single candidate. The rival closing
subsets are never constructed and therefore can never be reported as a tie —
**and no truncation flag is raised**, because nothing was truncated.

| line | engine subset | rival closing subsets | why unique |
|---|---|---|---|
| primary `bank[1]` | 22 rows, **2 debits** | 14 rows/1 debit, 13 rows/1 debit | more debits |
| primary `bank[8]` | 23 rows, **2 debits** | 15 rows/0 debits, 16 rows/0 debits | more debits |
| holdout `bank[11]` | 25 rows, **4 debits** | three subsets with 2 debits | more debits |
| holdout `bank[17]` | 20 rows, **10 debits** | six subsets with 4–7 debits | more debits |

**Stated plainly, as requested: the primary set's 1.000 precision is a property
of the dataset and the tie-breaker, not of the engine's ability to determine
the answer.** Only **7 of 12** primary credits had genuinely unique closure. On
the other 5 the engine was right because a modelling assumption — "defer as few
debits as possible", `DECISIONS.md` §4 — happened to select the true subset in
4 of 4 cases where it was decisive.

That assumption is the **same rule `SETTLEMENT_SPEC.md` §1.4 gave the simulator
that generated the data.** Solver and generator share a premise. `DECISIONS.md`
§1 argues Stage 3 can disagree with the attestation because the settlement
columns are withheld — true, and it does not cover this. The withheld columns
are data; the objective is a shared assumption, and no amount of column
withholding makes it independent evidence.

---

## 3. Consumption path audit (Task 3)

`DECISIONS.md` §2: *"It bounds which rows are candidates. It never chooses
among them."* **The first clause does not hold in code.**

`stage3_solver.run`:

```python
settlement_id = bank_to_batch.get(line.index)
if settlement_id:
    consumed |= {rows of that settlement}          # attestation-bounded, correct
elif isinstance(resolution, Determinate):
    consumed |= set(resolution.decomposition.row_ids)   # <-- UNGUARDED
```

The `elif` advances the pool on the **engine's own guess**, with no
corroboration of any kind.

| dataset | lines consuming on uncorroborated `Determinate` | rows consumed |
|---|---:|---:|
| primary | **0** | 0 |
| held-out | **3** (`bank[3]`, `bank[7]`, `bank[12]`) | **50** |

**All 12 primary bank lines are attested, so this branch is unreachable on the
primary set.** It executed for the first time on held-out data. A branch that
cannot execute on the only dataset in the repo is untested by construction, and
the 268-test suite passing said nothing about it.

**Resolutions consuming on a decomposition the attestation contradicts: 0 in
both datasets** — but only because on attested lines the code consumes the
*attested* rows rather than its own decomposition, so the two never collide.
The guard does not exist; the datasets merely fail to trigger it. The minimal
case in §0 *does* trigger it: an attested line whose `Determinate` includes two
rows the attestation excludes.

---

## 4. Why the postcondition never fired (Task 4)

**`Determinate.__post_init__` is unfalsifiable given its input.** It checks
`|decomposition.net − bank_amount| ≤ 0`. The only constructor is
`resolve_from_candidates`, fed exclusively by enumerators whose CP-SAT model
contains `sum(net_contribution·var) == target`. Every candidate satisfies the
equality by construction, so the residual is **identically zero**.

Measured: **18 `Determinate` resolutions across both datasets, 0 with non-zero
residual.** Not "it did not fire" — *it cannot fire from any code path in the
repository.* The only place it fires is a unit test that hand-builds an invalid
`BalanceProof` (`tests/test_solver_ambiguity.py:180`).

### Honest scope of the guarantee

`BalanceProof` proves exactly one thing: **the rows I selected sum to the bank
amount.** It cannot detect:

- a different set of rows also summing to that amount (D1);
- rows that belong to a *different* settlement (D2 — all 50 rows closed exactly);
- rows that settle nowhere at all (the §0 minimal case — 2 false positives, residual 0);
- a credit that was later reversed.

The repo currently implies more. `EVAL_REPORT.md` and `HOLDOUT_RESULTS.md` both
carry **"balance-identity violations: 0"** as a headline metric beside match
rate and precision, and `model.py` calls `BalanceProof` *"why a resolution is
believed"*. A quantity that is structurally incapable of being non-zero is not
evidence and should not sit in a headline table.

### What would have caught it, from solver-visible data alone

Both checks below use only columns already present in `recon_combined.json`.
`settlement_id`/`settlement_utr` are withheld from the *enumerator*, but
`stage3_solver.run` already reads `settlement_id` for consumption — so using
them as a **veto** (refusing a candidate) rather than a **selector** (choosing
among candidates) is consistent with the existing design boundary.

1. **UTR-contradiction veto.** If the chosen rows collectively declare a
   non-empty `settlement_utr` set *U*, the bank line has a non-blank UTR *u*,
   and *u ∉ U* — refuse `Determinate`. Measured: fires on exactly the 3
   reversal lines, **fires on nothing in the primary set**. The blank-UTR line
   and the null-UTR adjustment batch (class c12) both pass, because neither
   declares a contradicting UTR.
2. **Unfiltered-closure uniqueness.** Enumerate closing subsets *without* the
   deferral objective; `Determinate` only if genuinely unique. This is the only
   check that catches D1.

**Neither catches both.** Measured, not argued: the UTR veto leaves the §0
adjustment case wrong; unfiltered closure leaves all 50 reversal rows wrong.

---

## 5. Failure surface (Task 5)

Six minimal fixtures, real unmodified cascade. `investigation/sweep.py`.

| trigger | result | verdict |
|---|---|---|
| two credits, identical composition, same period | `Ambiguous` (4 cand.) then `Determinate` correct | safe |
| amount reachable by two disjoint similar-sized subsets | `Ambiguous` (6 cand.) | safe |
| duplicated payment row, same amount and day | `Ambiguous` (2 cand.) | safe |
| **partial settlement re-issued under a new UTR** | **`Determinate` WRONG** | **fails** |
| **adjustment exactly offsetting a payment in the pool** | **`Determinate` WRONG, 2 false positives** | **fails** |
| credit needing a row an earlier credit consumed | `Ambiguous` (3 cand.) then `Determinate` correct | safe |

The engine is safe where rival subsets **tie at the debit optimum** — then it
declines correctly. It fails where a rival subset exists but applies **fewer
debits**, because the objective silently discards it. That is the failure
surface, and it is defined by the objective, not by reversals.

---

## 6. Remediation options, costed on both datasets (Task 6)

Measured by re-implementing Stage 3's loop with policy switches
(`investigation/remediation.py`). The baseline policy reproduces the frozen
engine exactly — 96.55% / 0 wrong and 73.11% / 50 wrong — before any variant is
trusted.

| # | policy | primary | held-out | fixes | genuine fix or patch? |
|---|---|---|---|---|---|
| 0 | baseline | 96.55%, 0 wrong | 73.11%, **50 wrong** | — | — |
| 1a | require line attested before `Determinate` | **96.55%, 0 wrong** | **75.94%, 3 wrong** | D2 | partial — leaves D1 |
| 1b | **UTR-contradiction veto** | **96.55%, 0 wrong** | **75.94%, 3 wrong** | D2 | partial — leaves D1 |
| 2 | require attested composition match | **96.55%, 0 wrong** | **75.94%, 3 wrong** | D2, D1-when-attested | partial |
| 3 | never consume on uncorroborated `Determinate` | 96.55%, 0 wrong | 75.94%, **44 wrong** | propagation only | **not a fix** |
| 4 | reversal pre-pass | 96.55%, 0 wrong | 75.94%, 3 wrong | D2 only | **trigger-specific patch** |
| 5 | unfiltered-closure uniqueness | **67.00%**, 0 wrong | **40.57%, 50 wrong** | D1 only | partial, very costly |
| — | **1b + 5** | **67.00%, 0 wrong** | **40.57%, 0 wrong** | D1 + D2 | closest to sound |

Notes that matter more than the table:

- **Every attestation-based guard costs ZERO on the primary set** and *raises*
  held-out match rate (73.11% → 75.94%), because once credit A stops consuming,
  credit B reconstructs correctly. Placed-correctly rises 155 → 161. This is not
  a precision/recall trade — it is strictly better on both.
- **Option 3 alone is not a fix.** It stops the propagation but credit A still
  takes the rows: 44 wrong remain.
- **Option 4 is a trigger-specific patch** and the sweep proves it: it leaves
  the adjustment case wrong. It should not be adopted as *the* fix.
- **Option 5 is honest but brutal**: −29.55pp on the primary set, and it does
  **not** fix the reversals (still 50 wrong), because credit A's closure was
  unique. Its cost is concentrated in `Ambiguous` results with large candidate
  sets — the engine declining because the problem really is under-determined.
- **3 rows stay wrong under 1a/1b/2/4.** They are assigned through
  `Ambiguous.certain_rows` on `bank[5]`, not through `Determinate` — **defect
  D3**. Any fix scoped to `Determinate` leaves it.

### Recommendation for the fix decision (not implemented)

1. **Adopt 1b (UTR-contradiction veto) and extend the same veto to
   `Ambiguous.certain_rows`** — closes D2 and D3 at zero measured cost on the
   primary set and a gain on held-out.
2. **Stop reporting "balance-identity violations" as a headline metric.** It is
   structurally always zero. Replace with a check that can fail.
3. **Treat D1 as an open, disclosed soundness limit.** `Determinate` currently
   means "unique among max-deferral closing subsets." Either rename it to say
   so, or adopt option 5 and accept 67% on the primary set. **This is a real
   trade and should be a recorded decision, not a silent one.**
4. Option 5's cost is the honest measure of how under-determined this problem
   is. It is also the argument for the global/column-generation formulation in
   `DECISIONS.md` §2: corroboration beyond the sum is what buys back the
   precision, and per-credit enumeration has no access to it.

---

## 7. Verdict on the stated hypothesis

> *The absence of a reversal class is the trigger, not the defect. The defect is
> that `Determinate` is reachable on arithmetic alone.*

**Correct in substance, wrong in mechanism for the 50 rows — and the real
picture is worse.**

- **Confirmed:** `Determinate` is reachable without proof of correctness, and
  reversals are one trigger among an open-ended family. The adjustment case
  proves a non-reversal trigger produces a confident wrong answer, and a
  reversal-specific fix (option 4) demonstrably leaves it in place.
- **Confirmed and worse than stated:** the guarantee is weaker than "arithmetic
  alone." It is *objective-filtered* arithmetic — unique among subsets
  maximising applied debits. That admits `Determinate` on 2 primary credits
  that had 3 closing subsets each, and lets the objective *actively select* a
  wrong subset.
- **Refuted for the 50 rows:** they were **not** caused by under-determination.
  Closure was unique at all three lines (`OPTIMAL`, untruncated). Their cause is
  the unguarded consumption `elif` — a distinct defect, proved distinct by
  measurement: option 5 fixes D1 and leaves all 50 wrong; option 1b fixes D2
  and leaves the adjustment case wrong.
- **Additional defect not in the hypothesis:** `Ambiguous.certain_rows` is a
  third unguarded assignment path (D3).

**These are three separable defects. No single option in §6 fixes all three.**
