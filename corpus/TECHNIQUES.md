# TECHNIQUES — evaluation, not adoption

Five industry and literature techniques, assessed against what this engine
actually needs. For each: what it is, what it would fix **here**, what it
costs, and whether to adopt — with the measurement that supports or refutes
it wherever a claim about this domain is involved.

**Nothing here is implemented.** Two of the five are refuted by measurements
taken for this document. Adopting a technique because it is standard practice
is not a reason, and `DECISIONS.md` requires the rejected alternatives anyway.

---

## The constraint every technique is judged against

`DECISIONS.md` §39 fixed a defect where a truncated enumeration was recorded
as exhaustive. §44.8 generalised it: **a pool that is too small hides rivals,
and a hidden rival is indistinguishable from no rival**, so uniqueness is only
meaningful relative to a stated search space.

Therefore:

> **A faster way to get an unproven answer is worth nothing here.** Any
> technique that returns a good subset quickly without a certificate of
> exhaustiveness reintroduces §39's defect with better performance.

That single requirement decides three of the five evaluations below.

---

## 1. SSMP, set partitioning, and column generation

**Priority: highest — the only technique with a path to CLOSING something.**

### What it is

The problem has a name. **The Subset Sum Matching Problem (SSMP)**, Wu,
Torres, Zehtabi, Pozanco Lancho, Cashmore, Borrajo and Veloso, *J.P. Morgan
Quantitative Research / J.P. Morgan AI Research*, [arXiv:2508.19218](https://arxiv.org/abs/2508.19218),
August 2025. Formally: given multisets **a**, **b** and tolerance ε, find a set
of *matches* ⟨a_w, b_v⟩ with |w·a − v·b| ≤ ε whose inclusion vectors are
**pairwise disjoint** — which is exactly this engine's cross-line exclusivity —
maximising the number of matches and elements covered. Elements may belong to
no match. The decision problem is NP-complete by reduction from subset sum.

They give three algorithms: an **optimal MILP** (CPLEX, (M×K)+(N×K)+K binary
variables), a **search solver** (meet-in-the-middle with caching, O(2^(N−r) +
(1+ε)2^(M+r)) time, O(2^r + 2^(N−r)) space; at r=(N−M)/2 that is O(2^((M+N)/2))),
and a **pseudopolynomial DP solver**, O((M+N)·X) where X is the largest
matchable subset value.

### What it would fix here, and why it is now load-bearing

`DECISIONS.md` §2 measured the global set-partitioning ILP at 1,347 booleans
returning **UNKNOWN at 60s**, and named column generation rather than a bigger
time limit as the correct next step. §22 records that `Reconstructed`'s
cross-line exclusivity is necessary but not sufficient and that satisfying it
cheaply is open work. §46 (defect **D15**) makes the global formulation
load-bearing rather than optional: contract §2.4 gives consumption to
`Verified` alone, so at PSP absence nothing consumes, so the pool grows
monotonically to ~10× the true pool, so uniqueness over the true pool is not a
fair bar. **The gate and the consumption problem are one problem**, and a
tractable global formulation addresses both at once.

### The literature independently validates §2's measurement

This is worth stating plainly because it converts a local failure into a known
result: the SSMP paper's **optimal MILP times out at a 90-second allowance for
almost every configuration beyond M=N=10** (their Tables 1 and 2), on instances
far smaller than this corpus. §2's UNKNOWN at 60s on 1,347 booleans was **the
expected outcome of that formulation, not a defect in its implementation.**

Their experiments run to M, N ≤ 100. `datasets/A40_Bnone_Cmax` line 15 has a
derived pool of **414 rows**.

### Why column generation does not deliver what this engine needs

Branch-and-price solves the LP relaxation at each node by column generation and
is the exact method of choice for set partitioning when the variable count is
too large to enumerate ([Barnhart et al., *Branch-and-Price*](https://scispace.com/pdf/branch-and-price-column-generation-for-solving-huge-integer-4jvlny6blr.pdf);
[Mathematical Programming Computation 2023](https://link.springer.com/article/10.1007/s12532-023-00240-w)).

**It is an optimisation method. It returns an optimal solution.** This engine
deliberately has **no objective** — contract §2.1 forbids one filtering
candidates before uniqueness is tested, because an objective selecting among
rivals is exactly how defect D1 reported `Determinate` on batches with three
closing subsets. What this engine needs is the **complete candidate set with a
certificate**, so that "unique" is provable and "ambiguous" is reportable.

Column generation would tell us *the best* disjoint assignment. It would not
tell us *whether another one closes equally well*, which is the only question
the contract cares about. The SSMP paper's own algorithms are the same shape:
Algorithm 1 greedily finds **one** match at a time and stops. They do not
enumerate.

**Verdict: DO NOT ADOPT as the resolver's core.** It answers a different
question, faster.

### What would actually help, and it is a smaller idea

**Uniqueness testing is not enumeration.** To separate `Reconstructed` from
`Ambiguous`, the resolver does not need all closing subsets — it needs to know
whether **two** exist. Finding a second solution is enormously cheaper than
enumerating all of them, and it yields the same three-way verdict (`0`, `1`,
`≥2`) with a real certificate.

The pseudopolynomial route is credible for that, and the numbers are measured
rather than assumed. Bringmann's O(n+t) randomised algorithm
([arXiv:1610.04712](https://arxiv.org/pdf/1610.04712)) and Koiliaris–Xu's
Õ(√n·t) ([SODA '17](https://arxiv.org/pdf/1507.02318)) are pseudopolynomial in
the **target**, and on this corpus:

| | value |
|---|---:|
| payout target, median | **33,842,470** paise |
| payout target, max | **109,871,731** paise |
| true pool size, median / max | 25 / 80 |
| derived pool size, max | **414** |

O(n+t) is ~3.4×10⁷ operations at the median line and ~1.1×10⁸ at the worst —
tractable in C, marginal in Python, and **independent of pool size**, which is
the property that matters, since pool size is what breaks the current
enumeration at PSP absence.

**Caveat, and it is not small:** these are randomised algorithms and Bringmann's
is Monte-Carlo. A probabilistic certificate of uniqueness is not the same
object as CP-SAT's `OPTIMAL`, and §39 exists because a weaker epistemic state
was reported as a stronger one. Any adoption must state which it is.

### Verdict

**Do not build in this task, and do not build the branch-and-price version at
all.** The costed, researched gap is the deliverable:

* **Not worth building:** column generation / branch-and-price over the global
  set-partitioning formulation. It optimises; this engine enumerates. Cost
  would be weeks; the result would answer the wrong question.
* **Worth assessing further, separately:** a *uniqueness oracle* — decide
  whether ≥2 disjoint closing subsets exist, without enumerating — via a
  pseudopolynomial method. It attacks D15 directly, it is independent of pool
  size, and it must be honest about randomisation.
* **Named and not measured:** whether the SSMP paper's DP solver, applied
  per-line, beats CP-SAT at 414 rows. Their published sizes stop at 100.

---

## 2. Fellegi-Sunter match weights

### The blocking question, answered with a measurement first

FS's additive match weight — total weight = prior + Σ log₂(mᵢ/uᵢ) — is valid
**only under conditional independence of the comparison fields given match
status** ([Robin Linacre, *The mathematics of the Fellegi-Sunter model*](https://www.robinlinacre.com/maths_of_fellegi_sunter/)).
`DECISIONS.md` §21 measured a violation of exactly that on the frozen set. The
D4 fix was supposed to make the bank independent by construction. **Did it
carry to the corpus?**

Measured over all 28 datasets carrying a settlement column, 9,003 settled rows:

| test | result |
|---|---|
| §21's leak, `settlement_utr == str(settled_at) + settlement_id[-6:]` | **0 of 9,003 rows (0.0%)** — the D4 fix carried; this leak is gone |
| `settlement_id` → `settled_at` functionally determines | **1.000**, mean and min, all 28 datasets |
| `settled_at` → `settlement_id` | **1.000**, mean and min, all 28 datasets |
| `settlement_utr` → `settled_at` | 0.919 mean, 0.909 min |
| `settled_at` → `settlement_utr` | 0.376 mean, 0.083 min |

**Independence fails, and it fails structurally rather than through a
generator artefact.** The old leak is fixed. What remains is inherent to the
domain: *a batch has one formation time*, so `settlement_id` and `settled_at`
determine each other **totally and by definition**. An FS model treating
"agrees on `settlement_id`" and "agrees on `settled_at`" as independent
comparison columns would add two partial match weights for **one piece of
evidence**, and would report a confidence roughly the square of the truth.

That is not a defect FS can be configured around here. It is what the fields
mean.

### Verdict

**Adopt as a DIAGNOSTIC. Never as a decision rule.** And note this is a
stronger contribution than adoption would have been: the measurement above is a
result about this domain, not a configuration note.

What FS legitimately offers: term-frequency adjustment expresses that agreement
on a *rare* value is stronger evidence than agreement on a common one
([Splink's TF adjustments](https://moj-analytical-services.github.io/splink/topic_guides/comparisons/term-frequency.html)),
and Splink's waterfall chart explains an individual decision field by field
([waterfall chart](https://moj-analytical-services.github.io/splink/charts/waterfall_chart.html)).
That cardinality intuition is real and this engine has no equivalent.

What it cannot do here:

* **It cannot replace `rival_closure_count`.** They measure different things,
  and conflating them would be a category error. FS asks *how strong is the
  evidence for this pairing*; `rival_closure_count` asks *how many other
  pairings would have passed the same check*. A pairing can have overwhelming
  field agreement and 400 rivals — that is precisely the non-decisive
  `Verified` population, 239 of 275.
* **It does not transfer to the N:N case at all.** Standard record linkage is
  1:1 entity resolution over *pairs*. This engine resolves a bank credit
  against an unknown *subset*. There is no pair to score. FS could score the
  attested `settlement_id` → bank-reference link — which is already the Tier A
  join and is already exact — and nothing else.
* **Contract §8 and `DECISIONS.md` §20 reject a bare confidence float, and
  those rejections stand.** A weight may live *inside* an outcome. It may never
  replace one, and assignment may never become a threshold decision.

**Cost of the diagnostic version:** Splink on DuckDB over ~300–800 rows per
period is trivial to run and would produce one honest artefact — a measured
statement that this domain's comparison fields are not independent, with the
dependence quantified. That is roughly the table above, already produced,
without the dependency.

**Do not adopt Splink.** The measurement it would justify has been taken.

---

## 3. Blocking and date-window partitioning

### REFUTED BY MEASUREMENT

Industry practice partitions candidate pools by entity, currency, counterparty,
settlement id and **date** to stop combinations exploding, and the record
linkage literature has standard metrics for the trade: **pairs completeness**
(PC = matches retained inside blocks ÷ all true matches) and **reduction ratio**
(RR = 1 − comparisons made ÷ all possible), which trade against each other
directly ([TAILOR, ICDE 2002](https://www.cs.purdue.edu/homes/ake/pub/TAILOR_ICDE2002.pdf)).

The proposal was a date window on the pool: T+2 eligibility already gives a
lower bound, so add an upper one. **The measurement kills it.**

How far back a *true* composition reaches from its bank value date, over all
359 batches with a bank line:

| | days |
|---|---:|
| median | 9 |
| mean | 16.2 |
| p95 | 45 |
| **max** | **57** |

Batches whose true composition a window would **exclude** — i.e. `1 − PC`:

| window | batches whose truth is excluded | share |
|---|---:|---:|
| 7 days | 325 of 359 | **90.5%** |
| 14 days | 111 of 359 | **30.9%** |
| 30 days | 73 of 359 | **20.3%** |
| 60 days | 0 of 359 | 0.0% |

**The only window that never excludes the truth is one that spans the entire
observation period — which partitions nothing.** Pairs completeness reaches 1.0
only at reduction ratio 0.

The cause is not incidental. The selection rule settles the largest applicable
set of *eligible* rows, and rows that lose a round roll forward, so a batch
routinely contains a payment created weeks earlier. Rolling forward is the
domain, not noise.

### And it would be F1 reintroduced deliberately

`DECISIONS.md` §45 has just established that a pool too small hides rivals, and
§44.8 generalises it. **Partitioning shrinks the pool on purpose.** Any
proposal must say how it differs from F1, and on this data the honest answer is
that it does not: it trades a loud failure (non-unique closure, reported as
`Ambiguous`) for a silent one (the truth is not in the pool, reported as a
confident wrong answer).

**Verdict: DO NOT ADOPT on this data.** Not "adopt with a wide window" — a
window wide enough to be safe is not a partition. If pool growth is the
problem, the answer is a better *uniqueness test* (§1) or a consumption rule
that lets rows leave the pool (`CHECKPOINT.md` §12.4), not a smaller pool.

Recorded for a future dataset: if a corpus is ever generated where compositions
do not roll forward, this measurement must be re-taken before the conclusion is
reused. It is a fact about this data, not a theorem.

---

## 4. Cardinality vocabulary (1:1 / 1:N / N:1 / N:N)

**Verdict: ADOPT, reporting only, when someone next touches the report.**

1:1, 1:N, N:1 and N:N is standard reconciliation vocabulary, and **N:N — where
amounts agree only in combination — is the recognised hard case and is exactly
what this engine does.** Breaking the outcome accounting down by cardinality
would make the engine's capability legible to anyone from the industry in one
glance, and would very likely show the abstentions clustering in the N:N class,
which is the honest shape.

Cost: low. It is derivable from `Composition` — a one-row composition is 1:1
against its bank line, many-row is N:1 — and needs no behaviour change and no
contract change.

Why it is not done in this task: it is a reporting change with no measurement
behind it yet, and this task is an evaluation. It is the cheapest item on this
page and the only unambiguous adopt.

**One caution:** the breakdown must use the resolver's *claimed* composition,
not ground truth, or it becomes another figure that reads as a capability and
is really a property of the answer key.

---

## 5. Continuous / event-sourced reconciliation

### Re-examining §37's rejection in light of D15

`DECISIONS.md` §37 chose a two-pass reversal scan and **rejected** "refuse to
consume until the window closes" on the grounds that non-consumption drives
pool growth. That objection has since become defect **D15** — the central open
problem. The rejection was correct and was rejected *for the reason that is now
the problem*, which is worth re-reading rather than re-deciding.

### What the industry pattern actually is

The named pattern is Fowler's **Retroactive Event**, with three adjustment
strategies for a posting later found wrong: **Replacement** (delete and
re-post, simple, loses history), **Reversal** (post an opposite entry, keeps
history, doubles entries), and **Difference** (post only the delta, fewest
entries, hardest to implement) ([Fowler, *Accounting Patterns*](https://martinfowler.com/eaaDev/AccountingNarrative.html)).
The supporting mechanism is **bi-temporality**: record both when the event
occurred and when the ledger learned of it, so an as-at position stays correct
under backdated corrections.

**Bi-temporality is the direct answer to defect D13** — the `on_hold`
snapshot read against a past horizon — and to `DECISIONS.md` §44 generally.
D13 is currently open and bounded by the API: the Razorpay dispute entity
publishes no resolution timestamp (§44.5). Bi-temporality is what the feed
*would need* for that to be computable, which is worth stating as a
requirement on the data source rather than a design idea.

### Does it change the D15 analysis?

**No, and the reason is worth recording.** Event sourcing changes *when a
resolution may be revised*; D15 is about *how large the search space is when it
is first computed*. A revisable `Reconstructed` still has to be computed over a
265-row pool at the last credit. Making it revisable later does not make it
unique now.

Where it would genuinely help is the consumption rule: if a resolution can be
withdrawn, `Verified`-only consumption stops being the safety property it is,
because a wrong consumption becomes recoverable rather than permanent. That
weakens the argument for contract §2.4 — but §2.4 exists because defect D2 put
50 rows in the wrong place, and "we could have undone it" is a weaker guarantee
than "it could not happen".

**Verdict: §37's decision STANDS.** Nothing measured here overturns it.
Recorded as a named direction with one concrete, separable piece: **bi-temporal
timestamps on the dispute feed would close D13**, and that is a request to make
of the data source, not a change to make in this repository.

---

## Summary

| # | technique | verdict | decided by |
|---|---|---|---|
| 1 | branch-and-price / column generation over the global formulation | **do not adopt** | it optimises; this engine enumerates. Contract §2.1 forbids the objective it needs |
| 1b | pseudopolynomial *uniqueness oracle* (≥2 closing subsets?) | **assess further, separately** | independent of pool size, attacks D15 directly; randomisation must be disclosed |
| 2 | Fellegi-Sunter match weights | **diagnostic only, do not adopt Splink** | independence fails structurally: `settlement_id` ↔ `settled_at` at 1.000 |
| 3 | date-window partitioning | **do not adopt** | a 30-day window excludes the truth on 20.3% of batches; only a window that partitions nothing is safe |
| 4 | cardinality vocabulary 1:1 / N:N | **adopt** — reporting only | free, legible, no contract change |
| 5 | event-sourced reconciliation | **§37 stands** | it changes revisability, not search-space size. Bi-temporality would close D13 |

Two of the five are refuted by measurements taken for this document, and both
measurements are new results about this domain rather than notes about this
implementation. That is the useful output of the exercise.
