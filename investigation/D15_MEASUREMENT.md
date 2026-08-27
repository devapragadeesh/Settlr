# D15 — the measurement `DECISIONS.md` §46 named and did not take

Diagnostic only. Nothing was fixed, no gate changed, no frozen path touched.

§46 recorded that the closure register is scoped to a pool no resolver can
see, named the measurement that would settle whether the 15 G8 failures are
genuine abstention failures or correct refusals, and deliberately did not take
it. This is that measurement.

---

## 0. Lead: the answer is "correct refusals", and a reporting metric I added last phase is defective

**All 15 G8 failures are correct refusals.** At every one of them the resolver
*proved* that two or more closing subsets exist over the pool it can actually
see. Zero came back unique-and-complete. There is no genuine failure to fix.

**And the coverage metric I introduced in the previous phase has its own scope
error.** It counts a settlement line as "not attempted" when the resolver
returned `AttestationDiscrepancy` — that is, when it found a genuine record
contradiction and correctly declined to assert a composition. On the 28
non-absence datasets **all 60 unattempted lines are exactly that**, and all 62
`AttestationDiscrepancy` findings in the corpus are correct (0 genuinely
false). So the published coverage figure **penalises the resolver for detecting
the errors the benchmark planted**, and falls as the benchmark plants more of
them. That is the same class §44.8 and §47 are about, introduced by the
honesty pass that was supposed to remove it.

---

## 1. Coverage, decomposed exactly

### 1.3 Three scopes, each labelled

| scope | attempted / settlement lines | |
|---|---:|---|
| all 30 datasets | **276 / 359** | 76.9% |
| the 28 **non-absence** datasets | **275 / 335** | 82.1% |
| the 2 **absence** datasets alone | **1 / 24** | 4.2% |
| *(the original 14 only — the figure `THREE_SYSTEMS.md` publishes)* | *143 / 168* | *85.1%* |

The published **85%** is the original-14 scope. It is not the corpus-wide
figure and should not be read as one.

### 1.1 / 1.2 What the unattempted lines actually are

| | settlement lines | attempted | unattempted | of which `AttestationDiscrepancy` |
|---|---:|---:|---:|---:|
| 28 non-absence datasets | 335 | 275 | **60** | **60** |
| 2 absence datasets | 24 | 1 | 23 | 2 |
| total | 359 | 276 | 83 | 62 |

**Every unattempted line outside the absence datasets is an
`AttestationDiscrepancy`** — and the oracle's four-way split records **0
genuinely false** across all 62. Each one is a line where two sources
contradict each other and the contract forbids asserting a composition
(§4.2: *a discrepancy is a finding about the record, not a claim about which
rows settled*).

### 1.4 Stragglers outside the absence datasets: **zero**

The brief expected roughly two, on the reasoning that a small number of
stragglers in otherwise complete cells is where a cheap real fix could hide.
There are none. Re-stated on the population where a composition claim is the
appropriate answer at all, non-absence coverage is **275 / 275 = 100%**.

### The metric defect, stated precisely

`coverage = (Verified + Reconstructed) / settlement lines` treats three
different things as one:

* a line the resolver **answered** — `Verified` / `Reconstructed`;
* a line it **could not** answer — `Unresolved` / `Ambiguous`;
* a line it **must not** answer — `AttestationDiscrepancy`, where answering
  would mean asserting a composition the record contradicts.

Only the second is a coverage shortfall. Folding the third in means the metric
*declines as detection improves*: `datasets_v2` plants one false attestation
per dataset, the resolver catches 13 of 13, and its coverage drops from 85% to
79% **because it caught them**.

Recorded as a finding. Not fixed here — this task is diagnostic, and a
metric change is a reporting cycle of its own.

---

## 2. The D15 measurement

### The asymmetry that made it cheap

Proving a closure **unique** requires a complete enumeration — that is §39, and
an incomplete enumeration answers nothing. Proving a closure **not unique**
requires only **two** closing subsets, and truncation is irrelevant to it.

Every line below where the resolver found ≥2 subsets is therefore a *proof* of
non-uniqueness over the derived pool, whatever the enumeration's completeness
flag says. No new enumeration was needed for those.

### 2.2 Per line — all 18 reconstructible instances at the absence points

`key k` is the closure count in the answer key, over the pool the simulator
drew from. `found` is what the resolver's enumeration returned over the pool it
derived.

| dataset | line | key pool | **key k** | derived pool | **found** | complete | verdict |
|---|---:|---:|---:|---:|---:|---|---|
| `A20_Bnone_Cmax` | 0 | 3 | 1 | 8 | — | — | resolved (`Reconstructed`, not an abstention) |
| `A20_Bnone_Cmax` | 1 | 22 | 1 | 31 | **178** | **True** | **correct refusal — proven exhaustively** |
| `A20_Bnone_Cmax` | 5 | 14 | 1 | 56 | 200 | False | correct refusal |
| `A20_Bnone_Cmax` | 7 | 33 | 1 | 82 | 200 | False | correct refusal |
| `A20_Bnone_Cmax` | 9 | 15 | 1 | 108 | 9 | False | correct refusal |
| `A20_Bnone_Cmax` | 10 | 20 | 1 | 128 | 200 | False | correct refusal |
| `A20_Bnone_Cmax` | 12 | 18 | 1 | 153 | 200 | False | correct refusal |
| `A20_Bnone_Cmax` | 14 | 21 | 1 | 175 | 200 | False | correct refusal |
| `A20_Bnone_Cmax` | 16 | 15 | 1 | 217 | 200 | False | correct refusal |
| `A20_Bnone_Cmax` | 17 | 26 | 1 | 241 | 191 | False | correct refusal |
| `A20_Bnone_Cmax` | 18 | 23 | 1 | 270 | — | — | not an abstention (`AttestationDiscrepancy`, reversed credit) |
| `A40_Bnone_Cmax` | 0 | 6 | 1 | 8 | — | — | not an abstention (`AttestationDiscrepancy`, reversed credit) |
| `A40_Bnone_Cmax` | 2 | 40 | 1 | 58 | 200 | False | correct refusal |
| `A40_Bnone_Cmax` | 4 | 42 | 1 | 106 | 200 | False | correct refusal |
| `A40_Bnone_Cmax` | 5 | 41 | 1 | 164 | 200 | False | correct refusal |
| `A40_Bnone_Cmax` | 11 | 30 | 1 | 287 | 200 | False | correct refusal |
| `A40_Bnone_Cmax` | 12 | 35 | 1 | 334 | 200 | False | correct refusal |
| `A40_Bnone_Cmax` | 15 | 38 | 1 | 424 | 200 | False | correct refusal |

The 15 correct refusals are exactly the 15 G8 failures: 9 at
`A20_Bnone_Cmax`, 6 at `A40_Bnone_Cmax`, matching `violations_by_gate`.

### 2.3 Aggregate verdict

| verdict | count |
|---|---:|
| **correct refusal — ≥2 closing subsets PROVEN over the derived pool** | **15** |
| genuine failure — unique *and* complete over the derived pool | **0** |
| honestly unknown | **0** |
| not an abstention (1 `Reconstructed`, 2 `AttestationDiscrepancy`) | 3 |

### The cleanest single line: `A20_Bnone_Cmax` bank[1]

This one needs no caveat, because its enumeration **completed**:

```
answer key   : 1 closing subset   over the simulator's pool of 22 rows
resolver     : 178 closing subsets over its derived pool of 31 rows,
               status OPTIMAL — exhaustive, not truncated
```

Nine additional rows the resolver cannot rule out turn one answer into **178**.
The resolver did not fail to find the answer; **there are 178 answers**, and it
declined to pick one. Calling that an abstention failure is a statement about
the benchmark, not about the resolver.

### 2.5 No line to diagnose

No instance returned unique-and-complete over the derived pool, so there is no
genuine failure to trace. This was the branch that would have been the most
valuable finding, and it is empty.

---

## 3. Is anything cheaply fixable?

**No. Tasks 1 and 2 surfaced no genuine failure.**

* **The 15 G8 failures** are correct refusals. The resolver's behaviour is not
  at fault and no change to it would be an improvement — a change that made it
  answer these lines would be a change that made it guess among 178
  possibilities.
* **The 60 non-absence unattempted lines** are correct findings. Making the
  resolver "cover" them would mean asserting compositions the record
  contradicts.
* **The 2 absence datasets fail the oracle on a premise, not on behaviour.**
  G8's premise is uniqueness over the simulator's pool; §46's standing decision
  is that the gate is not loosened and the claim is rescoped. That decision
  stands and this measurement is what it was waiting for.

The one thing worth changing is a **metric**, not the engine: coverage should
separate *declined-because-contradicted* from *could-not-determine*. Cost:
small, reporting-only. Risk: none to scored behaviour. **Recommended, in a
reporting cycle of its own, not here.**

Not recommended: anything touching the pool, the cap or the time budget. §45
established that no pool change is local — moving a pool boundary moves rivals
in and out of view — and there is no failure here for such a change to fix.

---

## 4. A small artefact found while reconciling

`corpus/score_resolver.py:77` writes `report.violations[:12]` into
`oracle_results.json`. The stored `violations` list is therefore a **sample**,
and nothing in the file says so: at `A20_Bnone_Cmax` it holds 9 G3 and 3 G8
entries while `violations_by_gate` correctly records 9 and **9**. Reconciling
the two is what surfaced it.

`violations_by_gate` is authoritative and every gate figure in this repository
derives from it, so no published number is affected. Recorded because a
truncated field that does not announce its truncation is the same shape as
everything else in `DECISIONS.md` §44.
