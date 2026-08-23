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

*Not yet run. This section is written by `corpus/baseline_old_engine.py` after
the prediction above is committed, and reports what happened including where
the prediction was wrong.*
