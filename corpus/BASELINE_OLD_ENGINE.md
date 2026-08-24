# BASELINE — the frozen engine against the corpus

**Part 1 (the prediction) is committed in its own commit, before
`corpus/baseline_old_engine.py` is run even once.** The ordering is the
evidence and is visible in `git log`. `DECISIONS.md` §17 already established
that a prediction written after the fact is worth nothing; a prediction in an
editable file written the same afternoon would have been a regression from the
standard `holdout/SEED.txt` set, so it is committed the same way.

The engine under test is `matching/`, frozen at `81c04e0`, unmodified. The only
adaptation is a **column rename** on the bank file
(`bank_reference→utr`, `value_date→date`), documented in
`corpus/baseline_old_engine.py`. Every bank line is passed, including the
foreign credits, the foreign debits and the reversal debit.

**What this exercise is for.** The corpus is only trustworthy as a detector of
defects nobody has found if it can detect the ones we already know about. If
the old engine sails through, the corpus is wrong — not the engine.

---

## Part 1 — the prediction

Written before any run. Quantitative where a quantity is predictable, with the
reasoning attached, so that being wrong is informative rather than merely
embarrassing.

### P1. Foreign bank lines will be adopted, and this will be the largest single failure

**Predicted: 30–70% of foreign credits receive a confident `Determinate`, and
their rows are consumed.**

Mechanism, from `matching/stage3_solver.py`: `run()` iterates *every* bank line
and asks "which pool rows net to this amount?" It has no notion of a credit
that is not ours. A foreign credit carries a bank reference matching no
`settlement_utr`, so `bank_to_batch` has no entry, so `resolve_from_candidates`
returns whatever the enumerator found — and then the **unguarded `elif`**
consumes those rows on the engine's own guess (defect D2).

With pools around 20 and amounts on a price lattice, a subset netting to an
arbitrary foreign amount frequently exists. Each adoption then starves later
lines, so the damage compounds exactly as it did on the held-out reversal.

This failure mode **does not exist in the frozen primary dataset at all**: its
bank statement is a 12-line bijection with the 12 batches, containing zero
non-settlement credits and zero debits. It is the single largest thing the
frozen set could not test.

### P2. Confident wrong answers on attested lines, with no reversal present (D1)

**Predicted: ≥1 wrong `Determinate` on `A20_B100_Cmax`, rising with pool size;
at `A40_*`, 25–60% of resolved lines wrong.**

`enumerate_decompositions` maximises applied debits and enumerates only
solutions achieving that optimum, so rival closing subsets are never
constructed and no truncation flag is raised. The corpus records the closure
count per batch with **no objective**, so for the first time the rivals are
known to exist independently of the engine.

### P3. Degradation on `random_valid` but not on `max_under_cap` — premise sharing

**Predicted: wrong-`Determinate` rate at least 2× higher on
`A40_B100_Crandom` than on `A40_B100_Cmax`, and `A20_B100_Cfifo` in between.**

The engine's objective is `SETTLEMENT_SPEC.md` §1.4, the same rule that
generated `max_under_cap` data. `DECISIONS.md` §4 argues the objective only
bounds candidates; `investigation/DEFECT_REPORT.md` §2 measured that it was
**decisive on 4 of 4 primary credits where it mattered**. Under `random_valid`
there is no objective to share, so the tie-break stops being a free correct
answer.

*Stated risk to this prediction:* the falsifiable form of the premise-sharing
test (contract §6.2) needs the resolver's **rank-1 candidate**, and the old
engine does not expose one — it filters before enumerating, which is the
defect. So P3 will be measured through the cruder outcome-level proxy, and if
it comes out flat that is weak evidence, not absence of premise sharing.

### P4. Collapse as pool size passes 30, into `Unresolved` rather than into error

**Predicted: `Unresolved` share rises above 50% at `A40_*` and above 80% at
`A60_*`.**

`ENUMERATION_CAP = 32` with the comment *"this ledger's worst case is 2, so 32
leaves ample headroom"*. Above pool 30 the corpus measures median closure
counts far above 32, so enumeration truncates, and
`resolve_from_candidates` converts *truncated with one found* into
`Unresolved`.

**This is the abstention loophole made visible.** The hardest cells of the
corpus will produce the *cleanest* soundness numbers for the old engine, and
that is precisely why the contract gates `Unresolved` at zero on the determined
subpopulation (§6.1). Expect the old engine to look better at `A60` than at
`A20` on every soundness metric, and to be worse.

### P5. Wrong assignments through `certain_rows` (D3)

**Predicted: present on ≥2 datasets.** Any `Ambiguous` with a non-empty
`certain_rows` is an assignment made through an ambiguity *property*. The
contract has no vocabulary for it, so every occurrence is counted as an
unrepresentable claim.

### P6. `AttestationDiscrepancy`: zero detected of N planted

**Predicted: 0 detected on every dataset, with certainty rather than
probability.** Each dataset plants a settlement report whose amount disagrees
with the bank. The old engine has no outcome type that says "the record is
wrong" — its only vocabulary for trouble is `Unresolved`, which says "I could
not explain this". This is not a tuning gap; it is a missing concept.

### P7. Most confident answers will be unrepresentable in the contract

**Predicted: the count of unrepresentable claims exceeds the count of wrong
answers.** A `Determinate` on an unattested line cannot become `Reconstructed`
(no unfiltered uniqueness, no cross-line exclusivity) and cannot become
`Verified` (one party). It is not that the old engine's answers are wrong so
much as that **most of them are claims nothing in the record supports** —
including many that happen to be correct.

### What would falsify the corpus rather than the engine

If the old engine scored cleanly across the grid, the corpus would be the thing
at fault. Specifically:

* **0 foreign adoptions** would mean the foreign lines are trivially
  separable — a leak, and the audit should have caught it.
* **0 wrong `Determinate` anywhere** would mean closure is effectively unique
  everywhere, i.e. the corpus sits below the hard regime exactly as the frozen
  set does.
* **`Unresolved` near zero at `A60`** would mean pools never actually reached
  the intended size.

Each is checked in Part 2 and reported whether or not it is comfortable.

---

## Part 2 — the results

One run of the frozen `matching/` cascade (`81c04e0`, unmodified) over all 14
datasets, after the prediction above was committed. Numbers are from
`corpus/baseline_results.json`, written by `corpus/baseline_old_engine.py`.

| dataset | pool | Determinate | Ambiguous | Unresolved | wrong | foreign adopted | abstained on determined | unrepresentable | mean k |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `A10_B100_Cmax` | 10.17 | 12 | 0 | 8 | 0 | 0/8 | 0/11 | 0 | 1.0 |
| `A20_B0_Cmax` | 19.0 | 3 | 11 | 6 | 0 | 0/8 | 0/0 | 4 | 23.2 |
| `A20_B100_Cfifo` | 18.25 | 4 | 8 | 8 | 0 | 0/8 | 6/10 | 4 | 14.2 |
| `A20_B100_Cmax` | 19.0 | 6 | 6 | 8 | 0 | 0/8 | 5/10 | 5 | 6.9 |
| `A20_B100_Crandom` | 20.0 | 3 | 7 | 10 | 0 | 0/8 | 7/9 | 4 | 11.3 |
| `A20_B100_Crandom0` | 24.5 | 4 | 8 | 8 | 0 | 0/8 | 2/6 | 3 | 16.1 |
| `A20_B50_Cmax` | 18.92 | 6 | 6 | 8 | 0 | 0/8 | 3/4 | 9 | 4.5 |
| `A20_B75_Cmax` | 18.58 | 4 | 9 | 7 | 0 | 0/8 | 5/8 | 6 | 13.0 |
| `A30_B100_Cmax` | 28.58 | 4 | 7 | 9 | 0 | 0/8 | 6/9 | 4 | 15.4 |
| `A40_B100_Cfifo` | 35.33 | 5 | 7 | 8 | 0 | 1/8 | 3/6 | 3 | 16.2 |
| `A40_B100_Cmax` | 34.83 | 1 | 14 | 5 | 0 | 0/8 | 4/5 | 5 | 22.7 |
| `A40_B100_Crandom` | 35.0 | 2 | 9 | 9 | 0 | 0/8 | 6/7 | 1 | 24.1 |
| `A40_B50_Cmax` | 35.5 | 2 | 12 | 6 | 0 | 0/8 | 0/0 | 5 | 21.3 |
| `A60_B100_Cmax` | 51.83 | 1 | 8 | 11 | 0 | 0/8 | 2/3 | 3 | 21.7 |

**Totals:** 0 confident wrong answers · 1 of 112 foreign lines adopted ·
10 rows misplaced · **49 of 88 determined instances abstained** ·
56 unrepresentable claims.

---

### The headline, and it is not the one the prediction expected

**The frozen engine produced ZERO confident wrong answers across the entire
corpus — and abstained on 49 of the 88 bank lines the corpus proves have
exactly one answer.**

Read the first half alone and the engine looks sound. It is the second half
that says what actually happened: it did not avoid wrong answers by being
right, it avoided them by declining. On 56% of the instances where an
objective-free, complete enumeration proves a unique closing subset exists and
the attestation confirms it, the engine said nothing.

That is precisely the failure mode `RESOLVER_CONTRACT.md` §6.1 was written to
expose, and it is why the abstention gate exists. **An oracle with only
soundness gates would have scored this run perfectly.**

---

### Where the prediction was wrong

**P1 — WRONG, and badly.** Predicted 30–70% of foreign credits adopted with
rows consumed. Measured: **1 of 112**, on `A40_B100_Cfifo`, costing 10
misplaced rows.

The *mechanism* was right — `stage3_solver.run` does iterate every bank line
and has no notion of a credit that is not ours, and the one adoption proves the
branch is live and does consume. The *quantity* was badly wrong, for a reason I
should have seen: finding a subset of a 20–50 row pool that nets to an
**arbitrary** foreign amount is rare. Subset-sum to a target that no process
generated is usually unsatisfiable. I reasoned from "the guard is missing" to
"the guard will be hit often" without checking whether the input would reach
it.

The corpus still earns its keep here — the failure mode does not exist at all
in the frozen set, whose bank statement is a 12-line bijection with 12 batches.
But 1/112 is a rare-event class, and a corpus wanting to *measure* foreign-line
handling would need amounts chosen to be reachable, not merely unrelated. That
is a gap this run found in the corpus, not in the engine.

**P2 — WRONG.** Predicted ≥1 wrong `Determinate` on the spine and 25–60% wrong
at `A40_*`. Measured: **0 wrong `Determinate` anywhere.**

I named this in advance as a result that would falsify the **corpus** rather
than the engine: *"0 wrong Determinate anywhere would mean closure is
effectively unique everywhere, i.e. the corpus sits below the hard regime."*

**That reading is refuted by the rest of the run, and I am rejecting my own
falsification criterion on evidence.** Mean candidate set size runs 4.5–24.1
and `Ambiguous` reaches 14 of 20 lines; the corpus is emphatically not below
the hard regime. The engine did not answer correctly — it declined. The
criterion was wrong because it assumed an engine that answers; it does not
distinguish "the problem was easy" from "the solver refused the problem", and
those need different responses.

**P3 — UNTESTABLE, as flagged.** The outcome-level proxy is degenerate when the
wrong-answer rate is 0 everywhere. `Determinate` counts by rule at A20 are
Cmax 6 / Cfifo 4 / Crandom 3 and at A40 Cmax 1 / Cfifo 5 / Crandom 2 — noisy,
no clean signal, and not evidence either way. The falsifiable form (contract
§6.2, rank-1 hit rate in excess of chance) **cannot be computed for this
engine at all**, because it filters candidates before enumerating and so never
exposes a rank-1 pick. That is the defect, and it also makes the defect
unmeasurable by the statistic designed for it. Recorded as an open gap.

**P4 — RIGHT in direction, WRONG in mechanism.** Predicted `Unresolved` above
50% at `A40_*` and above 80% at `A60_*`. Measured `Unresolved` is 25% at
`A40_B100_Cmax` and 55% at `A60`. But the *collapse* is real and stronger than
predicted — the share of lines receiving no confident answer runs **70% at
pool 19, 95% at pool 35, 95% at pool 52**, against 40% at pool 10.

The mechanism was wrong: I said `ENUMERATION_CAP = 32` would truncate into
`Unresolved`. It mostly truncates into **`Ambiguous`** — `resolve_from_candidates`
only returns `Unresolved` when exactly one candidate is found *and* truncation
occurred. The collapse is into declared ambiguity, not into silence.

**The second half of P4 is confirmed exactly:** the engine looks *better* at
`A60` than at `A20` on every soundness metric — 0 wrong, 1 `Determinate` — and
is unambiguously worse. Without the abstention gate, the corpus's hardest cell
would be its cleanest-looking result.

**P5 — CONFIRMED, and it is the largest single category.** `certain_rows`
accounts for **45 of the 56** unrepresentable claims, on far more than the
predicted 2 datasets. Defect D3 is not an edge case in this engine; it is its
main assignment path once ambiguity dominates.

**P6 — CONFIRMED, with certainty rather than probability.** 0
`AttestationDiscrepancy` detected of 14 planted. The engine has no outcome type
that says *"the record is wrong"*. Not a tuning gap — a missing concept.

**P7 — CONFIRMED emphatically.** 56 unrepresentable claims against 0 wrong
answers. Broken down: **45 `certain_rows` assignments**, **9 `Determinate` on
unattested lines**, **1 `Determinate` on a foreign line**.

This is the finding that survives everything else. The old engine's problem is
not mainly that its answers are wrong — on this corpus none of them provably
are. It is that **most of its confident answers are claims nothing in the
record supports, including the ones that happen to be correct.** A `Determinate`
on an unattested line cannot become `Verified` (one party) and cannot become
`Reconstructed` (no unfiltered uniqueness, no cross-line exclusivity). The
contract has no vocabulary for it because there is no evidence for it.

---

### What this run says about the corpus

Two of seven predictions were wrong, one was untestable, and one had the wrong
mechanism. That is worth stating plainly rather than presenting four
confirmations as a clean sweep.

**The corpus detects what it was built to detect.** It exposed D3 as the
dominant assignment path (45 claims), proved the D2 consumption branch live
(the single foreign adoption, 10 rows), demonstrated the collapse with pool
size, and showed that `AttestationDiscrepancy` is unreachable for this
architecture. None of these are visible on the frozen primary set.

**And it found two things about itself.** The foreign-credit class is a
rare-event class as constructed — unrelated amounts are almost never reachable
from the pool, so it tests the *guard* without exercising it. And the
premise-sharing statistic cannot be computed against an engine that filters
before enumerating, which is exactly the engine it most needs to measure. Both
are recorded in `corpus/CORPUS_SPEC.md` §8 rather than left for a reader to
notice.
