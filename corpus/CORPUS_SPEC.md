# CORPUS_SPEC.md — the benchmark corpus

**Status:** normative for `corpus/`. Child document of
`engine/SETTLEMENT_SPEC.md`, which stays frozen and is cited rather than
forked. Where this document differs from it, the difference is stated as a
delta with a reason.

**What this is.** The evidence artifact a reconciliation engine is measured
against. Not a dataset — a family of datasets spanning a measured space, with
an isolated answer key, a leak search, and an oracle whose gates cannot all be
passed by answering nothing.

---

## 1. Why it exists: the primary dataset could not have found the defects

The previous engine reported **96.55% match rate and 1.000 precision** on the
frozen primary dataset and then produced **50 confident wrong answers** on
held-out data. `investigation/DEFECT_REPORT.md` found three engine defects. An
audit of the *data* found seven more, and the data defects matter more, because
they mean the primary dataset was **structurally incapable** of exposing the
engine defects.

Every row below is a measurement over `engine/data/`, reproducible with
`python3 corpus/leakage_audit.py --validate-frozen`.

| # | defect | measurement |
|---|---|---|
| **D4** | the bank statement is a re-encoding of the settlement record | `settlement_utr == str(settled_at) + settlement_id[-6:]` on **11 of 11** batches; narration embeds the UTR verbatim on **9 of 12** lines; posting lag **0 days, always**; 12 distinct dates for 12 lines |
| **D5** | calibration rows are greppable | `description == 'Settlement processing fee'` isolates minted rows at precision **1.000**; and the `amount` column alone separates them — 4 minted debits at 1,200,573–3,295,351 paise against every organic adjustment at 3,195–39,197 |
| **D6** | orphan ERP invoices are sortable | the **6 highest invoice numbers** are exactly the 6 orphans, precision 1.000 recall 1.000, 30.7× lift |
| **D7** | the decoy class exercises nothing | the 4 planted pairs have credit deltas **−8,711 / −3,670 / 0 / +11,732** — 1 of 4 collides, and it collides *by accident*, alongside 3 non-decoy pairs |
| **D8** | `source_ref` is still a class marker | `'recon sample adj_EhcHONhX4ChgNC shape'` → `c09_lost_dispute_adjustment` at precision 1.000, recall 1.000 |
| **D9** | the GST leg has no reconciliation work | 20-row file; all 3 ITC findings are single-column filters at precision 1.000; `itc_availability == 'No'` supplies the conclusion as an input column |
| **D10** | the bank statement is a bijection with the batch list | 12 lines, 12 batches, one per batch, zero foreign credits, zero debits, 12 distinct dates, all Wednesdays |

Plus: **max pool size 26**, while closure uniqueness only collapses above ~30;
and **attestation coverage 100%**, so the code path that produced all 50 wrong
answers was *unreachable*.

### Three corrections to the received account of these defects

Recorded because being precise about a defect is the difference between fixing
it and fixing something adjacent to it.

**D6 is an ordinal leak, not a position leak.** The orphans are *not* appended:
they sit at file positions 45, 65, 74, 102, 143 and 161 of 184 — interleaved.
What gives them away is that `invoice_no` is monotone in `invoice_date` for
every non-orphan, so the orphans hold the six highest numbers. **A
file-position check passes this dataset.** The audit therefore tests ordinal
rank over every field, not file position.

**D7 fails 3 times in 4, and its one success is an accident.** Only
`pay_VhCW46ocAQWSbM` / `pay_H9TWqp5H61RhiE` collide on credit — and three
*non-decoy* pairs collide for the same reason, so the class's single success is
indistinguishable from the accidents beside it.

**D10's mechanism is not file order.** Measured: shuffling
`bank_statement.csv` changes the cascade's output not at all (196/12/9/3 both
ways), because `stage3_solver.run` re-sorts by `value_date`. The defect is
stronger and different — **unique dates at zero posting lag mean date-sorting
alone recovers the exact true settlement sequence**, and a same-day collision
is structurally impossible. Fixing "file order" would have fixed nothing.

---

## 2. The formulation error the corpus must be able to detect

The old engine asked: *given a bank credit and a pool, find the subset that
sums to it.* That question has no unique answer — above 30-row pools, 100% of
credits had multiple closing subsets, median 73–175.

The engine hid this by filtering candidates through a max-applied-debits
objective, so rival subsets were **never constructed** and could never surface
as ties. And that objective is `SETTLEMENT_SPEC.md` §1.4 — the same rule that
generated the data. **Solver and generator shared a premise.**

The corpus makes that class of error impossible to hide, three ways:

1. every batch carries a closure register built with **no objective at all**
   (§4), so rivals exist in the key independently of any solver;
2. axis C varies the generator's rule, including one with no objective, so a
   shared premise stops being free (§6.3);
3. the contract forbids an objective from filtering before uniqueness is
   tested, and the oracle measures **rank-1 hit rate in excess of chance**,
   which is defined even on instances a sound resolver correctly declines.

---

## 3. The artefacts

    recon_combined.json     PSP ledger rows. settlement_id ALWAYS populated.
    settlement_report.csv   the PSP's ATTESTATION, as its own artefact.
    bank_statement.csv      the BANK's record. Independent — see §5.
    erp_orders.csv          the merchant's sales ledger.
    gstr2b.csv              the tax authority's inward-supply statement.
    disputes.json           issuer-originated dispute records.
    ground_truth.json       ISOLATED. No resolver may read it.
    DATASET_HASHES.txt      sha256 of all of the above.
    GENERATION_REPORT.md    what was achieved, per dataset.

**Why the attestation is its own file.** Two linkages are habitually
conflated: *row → batch* (`settlement_id` on the recon rows, the merchant
ledger's own claim) and *bank line → batch* (a shared reference, the
cross-source attestation, and the thing `stage3_solver.run` consumes). Axis B
varies **the second only**. Blanking row-level `settlement_id` would destroy
the merchant's own ledger and change the Stage-1 join rate, moving two
variables at once so that no axis-B result would be attributable to axis B.

Splitting them is also simply more realistic: a merchant receives a settlement
report from the PSP *and*, separately, a bank statement. Reconciliation is the
join of the two.

---

## 4. Ground truth: two facts, deliberately separated

The frozen key conflates them. The corpus key does not.

| field | what it is | known at pool 60? |
|---|---|---|
| `composition` | the subset the generator selected. A fact about the **generative process**. | yes, exactly |
| `closure` | every subset of the pool closing to the payout, **no objective**. A fact about the **reconstruction problem**. | no — capped, and it says so |

`closure.recoverable ∈ {unique, not_unique, unknown, no_closure}`, and
**`unknown` is first-class**. The harness must be able to say *"we prove
non-uniqueness in 34 of 40; in 6 we could not decide within budget, excluded
from the statistic and reported separately."* That is defensible.
*"We enumerated 500 and called it ambiguous"* is not — 500-of-many and 2-of-2
are both "ambiguous" and are not the same claim.

**A solver returning a confident answer where `closure.count > 1` is wrong even
when it matches `composition`, because it cannot have known.** That is
`SETTLEMENT_SPEC.md` §2's ambiguity contract, generalised and made scoreable.

`composition_closes` is asserted at generation, not reported: the true
composition summing to the payout is O(1) to check and a failure would mean the
generator is broken. `truth_in_closure` is **three-valued**, because "the truth
is not in the register" and "the register stopped before it could look" are
different statements and only the first would be a defect.

### Determined instances

A bank line is *determined* when closure is unique under a complete
objective-free enumeration, the attestation is present, and the attestation is
correct. These are exported as `determined_instances` and are the subpopulation
on which `Unresolved` is a **defect**, gated at zero by the contract §6.1.

Without them, every guarantee in the contract is satisfied by a resolver that
answers nothing — and since enumeration truncates first on the biggest pools,
the corpus's hardest cells would produce its cleanest numbers.

---

## 5. Bank independence: where the line is

> A bank field may **correlate** with a ledger field through a modelled
> physical mechanism. A bank field may not be **computed from** a ledger field.

Permitted, enumerated:

1. **amount** — the credit is the credit. This *must* leak; it is the join
   evidence and the reason reconciliation is possible at all.
2. **posting date within a few days of settlement** — money really does land
   near the settlement date.
3. **counterparty text naming Razorpay** — it really is the remitter.

The guarantee is structural: `corpus/generator/bank.py` takes a `Payout`
carrying an amount and a timestamp and **nothing else** — no settlement id, no
entity ids, no `Batch`. Compare `engine/generator.build_bank_statement`, which
receives `Batch` objects and writes `b.utr` into two columns.

The bank has its own counter with its own **gaps** (the branch clears other
customers' NEFT too), a posting lag that crosses weekends, narration templates
that sometimes omit the reference entirely, foreign credits and debits, and its
own ordering.

**Honesty boundary.** You cannot test *"no function from bank line to ledger
field exists."* You can test that an enumerated family does not exist, and you
can make the structural argument that the generator never receives the input.
That pairing is the defensible position; claiming the universal negative is
not, and a reader would find the gap in ten seconds.

---

## 6. The axes

A **screening design**, not the full 5 × 4 × 3 = 60 grid: a spine at the
configuration closest to the frozen set, then one factor moved at a time, plus
two interaction cells chosen for cause. 14 datasets. Untested interactions are
named in §8 rather than left implicit.

### 6.1 Axis A — pool size: 10 / 20 / 30 / 40 / 60

Spans the measured regime where closure uniqueness collapses. The frozen set
maxes out at 26 and therefore sits **entirely below** it.

Pool size is controlled **upstream**, by arrival volume and batch cadence.
Never by a minted row — that is D5, and it leaks.

*What it detects:* whether a resolver's confidence tracks the actual
determinacy of the problem, and whether it degrades into **error** or into
**honest abstention** as determinacy falls.

### 6.2 Axis B — attestation coverage: 100% / 75% / 50% / 0%

100% is the old world. The branch that produced all 50 wrong rows is
*unreachable* at 100%, which is why the frozen set could not find it.

Which settlements lose attestation is a **seeded uniform sample** — not the
largest, not the ambiguous ones. Coverage correlated with difficulty would
confound the axis with the thing it measures.

*What it detects:* whether a resolver's consumption rule survives losing its
corroborating source.

**At 0%, `Verified` is provably empty** (contract §6.3) — only the PSP attests
to composition, so with no attestation there is no composition claim to
corroborate. This is stated in advance as a theorem and gated, so the cell
teaches something rather than confirming an assumption. It follows that the 0%
cell measures **abstention discipline, not resolution**, and that axis B does
its real work at 75% and 50%. Both are limitations and both are recorded.

### 6.3 Axis C — generator selection rule

`max_under_cap` (reading B) / `fifo_under_cap` (reading E) / `random_valid`.

**The premise-sharing test.** `random_valid` is the important one: uniform over
feasible subsets in a band below the cap, with **no objective any solver could
share**, plus one axis point at φ=0 as the premise-free extreme.

*Stated honestly:* "a sound resolver scores flat across all three" is
**unfalsifiable as written**. At pool 40–60 under `random_valid` a sound
resolver returns `Ambiguous` almost everywhere, so every outcome-level metric
is flat under both hypotheses. The falsifiable form is contract §6.2 —
**rank-1 hit rate in excess of chance over multi-closure instances** — which is
defined even where the resolver correctly declines, is 0 under the null for all
three rules, and cannot be flat-at-zero for a trivial reason.

*Flagged assumption:* at φ=0.9 the rule still weakly shares "bigger is likelier"
with any resolver preferring large closing subsets. φ trades economic realism
against premise independence, is recorded per dataset, and was calibrated
against **measured mean pool size only, before any resolver existed**.

### 6.4 Axis D — adversarial classes

Present on every dataset, not a separate axis point:

| class | what it exercises |
|---|---|
| adjustment exactly offsetting a payment in the pool | D1 with **no reversal present** — the frozen engine returns `Determinate` with 2 false positives |
| settlement reversal, re-settled later | one reversal damages two bank lines |
| **foreign bank lines** (credits, debits) | *"is this credit even ours?"* — a question the frozen set cannot ask |
| **attestation that is WRONG** | the only thing that can produce `AttestationDiscrepancy` |
| duplicated payment rows | same credit, same day, different ids |
| decoys colliding on **credit** + 1–2 paise near-collisions | tolerance boundaries; D7's fix |
| ERP gaps both directions, orphans interleaved | D6's fix |
| dispute holds, clawbacks, roll-forward, netting, cross-month, schema variance, corrupt narration, the three ITC grounds | carried over from the frozen set |

---

## 7. The leak search, and why it is a search

Four leaks, four readers, closed one at a time — `source_ref`, `notes.reason`,
the orphan ordinal, and the calibration rows. **The fifth will not be a token.**
So `corpus/leakage_audit.py` does not ask *"does the string 'calibration'
appear"*; it asks whether **any** predicate over the solver-visible columns
separates a planted class from the organic population better than chance:
every single column, every column pair, ordinal rank on every field, string /
arithmetic / functional derivability, and a KS test per numeric column.

Plus a fifth family the other four cannot express: **class efficacy**. D7 is
not a leak — it is a class that is perfectly well hidden and simply does not do
what it claims. A separator search cannot find that, because there is nothing
to find.

### Why the build gates on effect size and reports significance separately

Measured: `description == 'Settlement processing fee'` reaches precision 1.000
at recall 0.500 over the six frozen minted rows — p = 8.79e-06 against a
Bonferroni α of 3.79e-06 over 2,641 single-column hypotheses. **It misses
significance by a factor of 2.3, and it is a leak anyone can exploit in ten
seconds.** A six-row class in a 240-row file cannot be certified by a
thousands-of-hypotheses search; that is a statement about power, not about the
rows being clean.

The costs are asymmetric — a false alarm costs one regeneration, a missed leak
costs the submission — so the gate is **precision and recall**, with the
p-value reported beside it as `certified` and underpowered classes named as
underpowered rather than reported clean.

### The audit found five problems in THIS corpus, which is the better evidence

Rediscovering known defects shows the audit is sensitive. Finding *unknown*
ones is what it is for, and across four regeneration rounds it found five —
three real leaks in the data and two flaws in its own statistics:

1. **A real leak.** Orphan ERP invoices were emitted with a blank `order_id`,
   so `order_id IS NULL/blank` isolated the class at precision 1.000, recall
   1.000 — a cleaner separator than the D6 defect it was written to prevent.
   Fixed: an orphan now carries an order reference in the merchant's own
   format, drawn from the same alphabet and length as a gateway order id. What
   makes it an orphan is that **no payment references it**, which is the
   reconciliation work rather than a shortcut to the label.
2. **A badly expressed class.** `d03_wrong_attestation` was expressed as the
   *rows of* the mis-attested batch, and every batch is trivially identified by
   `settled_at`. The separator was real and said nothing about the attestation
   being wrong. Now expressed at the settlement level, where the class is
   smaller than `MIN_CLASS_SIZE` and is reported **UNTESTABLE** — the honest
   answer rather than a flattering one.
3. **A class too small to be distinguishable from coincidence.** With three
   duplicate-payment pairs, one pair is 33% of the class and two are 67%, so a
   predicate keying on a single shared `(amount, issuer)` value cleared the 50%
   recall bar by luck. A duplicate is *defined* by sharing values with its
   twin, so the class is inherently somewhat self-identifying; the fix is to
   make it large enough that no single value predicate covers half of it.
4. **A second real leak: `narration CONTAINS 'clo'`.** Every foreign bank
   credit named a different remitter, so *"is this credit even ours?"* was
   answerable by reading the counterparty rather than by reconciling. Half the
   foreign credits now come from Razorpay too — a fee refund, a reversal
   re-credit, an advance. A merchant genuinely **can** rule out a credit from
   an unrelated payer; what the corpus must not do is make that the only case.

5. **A third real leak, and the subtlest.** Unattested settlements were
   reported under a `RZPX…` reference while attested ones carried the bank's
   `RATN…`, so sorting `reported_reference` separated them at precision 1.000.
   A real PSP's internal reference genuinely *does* look different from a bank
   UTR, so the separator was realistic — and realism is not the test. The test
   is whether a field reveals the generator's intent, and a prefix that exists
   to mean *"this one is in the withheld group"* does. The internal reference
   now takes a real bank reference's shape and differs only in being a value
   the bank never issued.

And two flaws in the audit's own statistics, found the same way:

* **Unit of analysis.** `d04_unattested_settlements` was scored over the *rows
  of* unattested batches, so a time-window predicate reached 94% precision on
  69% of them with a p-value treating ~69 clustered rows as independent. They
  are one observation repeated. Attestation is a property of a **settlement**,
  and the class is now expressed there.
* **Base rate.** At 0% coverage every settled row is unattested, so
  `settled == True` reached precision 1.000 / recall 1.000 at lift **1.2×** —
  not a leak, the definition of the axis point. The audit now requires
  `MIN_LIFT = 2.0` and reports a class covering more than half its table as
  **DEGENERATE** rather than as clean or as leaking.

**A dataset that fails its own audit does not ship.** All three were fixed and
the corpus regenerated at the same committed seeds — fixing a bug is not
reselecting a seed.

### The audit is validated against the frozen set

`python3 corpus/leakage_audit.py --validate-frozen` must rediscover **D4, D5,
D6 and D7 without being told what to look for**. It does. An audit that cannot
find known leaks proves nothing about the ones nobody has found.

The D5 class is derived by driving the frozen generator as a library and
diffing the row ids across the calibration planter calls — deriving it from the
leak itself would assume the answer the audit is meant to find.

---

## 8. What is NOT covered

Silence reads as ignorance. Everything below was considered and decided.

### Named gaps

**The GST leg is barely improved, and D9 stands.** All four axes are
settlement-side. The corpus widens the 2B file and stops `itc_availability`
from being a perfect proxy for the finding, but there is still no *volume* of
ITC decisions, no partially-filed-supplier population, and no IRN timing
distribution. **Any GST claim in a headline remains substantially unearned**,
and the fix is a fifth axis this corpus does not have.

**No wrong-**bank**-side class.** Axis D plants an attestation that is wrong.
It does *not* plant a case where the two sources contradict and **truth is on
the bank side** — a bank splitting one settlement into two credits, or posting
an amount that disagrees with a correct batch. So "two independent sources
agree" is never tested at the one point where the direction of the disagreement
matters. This is the most significant single gap.

**The full grid is not run.** 14 of 60 cells. A × C interactions beyond
`A40_B100_Crandom` are untested, and B × C entirely so.

**`Reconstructed`'s cross-line exclusivity is necessary, not sufficient.** A
credit that has not posted yet, or falls outside the window, cannot be excluded
against. `DECISIONS.md` §2 records that the global formulation returned UNKNOWN
at 60s on 1,347 booleans, so satisfying this cheaply is open work, not a solved
problem.

**Uniform sampling is claimed only where it holds.** `random_valid`'s counting
DP is exactly uniform over the band at these pool sizes. Above them a
CP-SAT-based sampler would inherit its search order, and the corpus records the
sampler per batch rather than asserting a distribution property the
implementation lacks.

**The foreign-credit class is a rare-event class as built.** Measured on the
baseline run: the frozen engine adopted **1 of 112** foreign bank lines. The
amounts are drawn independently of the ledger, and a subset of a 20–50 row pool
almost never nets to a target no process generated — so the class tests that
the *guard* is missing without ever exercising it. A corpus wanting to
**measure** foreign-line handling would need foreign amounts chosen to be
reachable from the pool, not merely unrelated to it. Found by running the
baseline, recorded rather than left for a reader to notice.

**The premise-sharing statistic cannot be computed against the engine it most
needs to measure.** Contract §6.2 needs the resolver's rank-1 candidate. The
frozen cascade filters candidates *before* enumerating — which is the defect —
so it never exposes one, and axis C falls back to an outcome-level proxy that
is degenerate when the wrong-answer rate is zero. The statistic is sound for a
resolver that obeys the contract and blind to one that does not.

**No resolver exists.** Deliberately. Building the corpus and the resolver
together is how the resolver ends up shaped to the corpus. The contract was
committed first, the corpus second; the resolver is separate work.

**Two implementations of one spec.** `corpus/generator/sim.py` re-implements
the batch-formation loop. The drift risk is real and is closed by differential
test against the frozen simulator — 29/29 passing on the frozen ledger under
both rules and on 25 seeded random ledgers — not by review.

### Out of scope, with the reason

Inherited from `SETTLEMENT_SPEC.md` §10 and unchanged: instant settlements
(blocked server-side in test mode), Route transfers, international and
multi-currency, TDS u/s 194-O, TCS u/s 52, negotiated pricing tiers.

---

## 9. Determinism and freeze

Every dataset is a pure function of one integer, and every seed was committed
in `corpus/SEEDS.txt` **before any data existed** — verifiable from `git log`.
Seeds are never reselected and no sweep is run. If a dataset comes out awkward
it is reported as it is, or a *bug* is fixed; the seed is not changed.

The one parameter calibrated after a measurement is the **price lattice
granularity**, and it is recorded rather than adjusted quietly: the first draft
put the whole corpus *above* the hard regime — at pool ~20, 11 of 12 credits
had multiple closing subsets and 7 of 12 exceeded 500 — which collapses axis A
and is the mirror image of the frozen set's flaw. It was calibrated against
measured closure counts, **before any resolver existed**, so nothing about
resolver performance was observable when it was picked. Same ordering
discipline as φ and the seeds.

Nothing under `engine/data/`, `engine/ground_truth/`, `engine/simulator.py`,
`engine/generator.py`, `engine/DATASET_HASHES.txt` or `matching/` is modified.
The frozen generator and simulator are **imported as libraries**; the frozen
cascade is run unmodified as the baseline the corpus must fail.
