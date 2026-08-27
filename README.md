# Settlement Truth Engine

Reconciles a payment ledger against a bank statement, an ERP order book and
GSTR-2B, and — the part that matters — **says what it does not know.**

> The measured work is **settlement-side only**. Every benchmark axis varies
> pool size, attestation coverage and selection rule; none varies anything
> about GST. **No GST or ITC claim in this repository is demonstrated** — see
> *The GST leg is not earned* below.

A settlement batch is a *subset* of eligible payments, net of refunds and
adjustments: Razorpay's own documentation states that "when settling
transactions, we will only choose the ones that add up to your current live
balance." So a bank credit of ₹99,329.23 does not identify which of the 21
eligible ledger rows composed it. Often several different subsets close to the
same amount. A reconciliation engine that always names one is guessing on most
of them and cannot tell you which.

This repository is two things:

1. a **resolver** that assigns rows to bank credits only when it can state what
   evidence supports the assignment, and declines with a reason otherwise;
2. a **benchmark** that can tell whether any resolver — including this one — is
   lying, built before the resolver and never tuned against it.

The second exists because the first version of this project reported **96.55%
match rate at 1.000 precision** on its own dataset, and then produced **50
confident wrong answers** the first time it saw data it had not been built
against. Both numbers were true. Neither meant anything, because the dataset
was structurally incapable of exposing the engine's defects. Everything here
follows from taking that seriously.

---

## What was evaluated and not built

**[`corpus/TECHNIQUES.md`](corpus/TECHNIQUES.md)** assesses five industry and
literature techniques against what this engine needs. **Two are refuted by
measurements taken for that document** — date-window partitioning excludes the
true composition on 20.3% of batches at 30 days, and Fellegi-Sunter's
independence assumption fails structurally here because `settlement_id` and
`settled_at` determine each other at 1.000. Both refutations are results about
the domain, not notes about this implementation.

## Every number in one place

**[`CLAIMS.md`](CLAIMS.md)** lists every quantitative claim this repository
makes with its denominator, its scope, the artefact that produces it and the
command that reproduces it — including the claims that **cannot** be
regenerated, which are flagged as such. It is generated, so it cannot drift
from the runs. If a number anywhere else disagrees with it, that number is
stale.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 run_all.py            # all three systems, every dataset (30-60 min)
```

`run_all.py` runs three systems over every dataset and writes
`corpus/THREE_SYSTEMS.md`. Nothing in this repo hand-writes a number into a
markdown file; every figure below is produced by a script from a live run.

Individual pieces:

```bash
pytest tests engine/tests corpus/tests resolver/tests -q   # the full suite
python3 -m resolver.run --all                              # resolver only
python3 corpus/triviality_check.py --all                   # is the task trivial?
python3 corpus/leakage_audit.py --all                      # is the data leaking?
```

---

## The three systems

| system | what it does |
|---|---|
| **naive GROUP BY** | groups recon rows by `settlement_id`, nets credit − debit, matches the total to a bank credit. Fifteen lines. Trusts the PSP completely. |
| **frozen cascade** | the previous engine: exact join → fuzzy → CP-SAT subset-sum under an objective → exception routing. No evidence model. Three known defects, unpatched, documented. |
| **new resolver** | evidence-tiered. Assigns only with a warrant naming which parties the evidence came from, and reports the number of rival compositions that would have passed the same check. |

The full per-dataset table, generated: **[`corpus/THREE_SYSTEMS.md`](corpus/THREE_SYSTEMS.md)**.

<!-- THREE-SYSTEM-SUMMARY:START -->
| dataset family | naive `GROUP BY` | frozen cascade | new resolver |
|---|---|---|---|
| **original 14** | coverage **168/168 (100%)**<br>168/168 right, **0 wrong**<br>abstained 0/88 det, 0/31 rec<br>discrepancies 0/13 | coverage **56/168 (33%)**<br>55/56 right, **1 wrong**<br>abstained 50/88 det, 16/31 rec<br>discrepancies 0/13 | coverage **143/168 (85%)**<br>143/143 right, **0 wrong**<br>abstained 0/88 det, 0/31 rec<br>discrepancies 13/13 |
| **PSP absent (2)** | **cannot run** | **cannot run** | coverage **1/24 (4%)**<br>1/1 right, **0 wrong**<br>abstained 0/0 det, 15/18 rec<br>discrepancies 0/0 |
| **false attestation (14)** | coverage **167/167 (100%)**<br>154/167 right, **13 wrong**<br>abstained 0/76 det, 0/43 rec<br>discrepancies 0/26 | coverage **50/167 (30%)**<br>48/50 right, **2 wrong**<br>abstained 42/76 det, 29/43 rec<br>discrepancies 0/26 | coverage **132/167 (79%)**<br>132/132 right, **0 wrong**<br>abstained 0/76 det, 0/43 rec<br>discrepancies 24/26 |

**Read coverage first.** *coverage* is settlement lines attempted out of settlement lines present — the denominator all three systems face. *right/attempted* is compositions exactly correct **out of the lines that system tried**, so it says nothing about the ones it declined; a system that declines a line and a system that answers it correctly look identical in that ratio. *abstained* is silence on instances that have exactly one answer — oracle gates G7 and G8, and **G8’s uniqueness is scoped to the pool the simulator drew from, 1.4×–14× smaller than the pool the resolver searches** (`DECISIONS.md` §46). *discrepancies* is planted record errors found, and the reported total is larger than the planted total because reversals are real findings the corpus did not plant — the genuinely-false count is **zero**. Full table: [`corpus/THREE_SYSTEMS.md`](corpus/THREE_SYSTEMS.md).
<!-- THREE-SYSTEM-SUMMARY:END -->

### The uncomfortable result first

**On the original fourteen datasets the naive `GROUP BY` wins outright** — 168
of 168 compositions, 0 wrong, 100% coverage, abstaining on none of the 88
determined and 31 reconstructible instances. That is not a fact about the
resolvers. It is a fact about those datasets: `settlement_id` is populated on
every settled row and none of them ever plants a false one, so trusting the PSP
is perfectly calibrated there and the benchmark cannot tell a sound resolver
from a credulous one (`CHECKPOINT.md` §0.1).

**The fifteen-line version is right until the record is wrong — and then it is
confidently wrong and cannot tell you.** On the fourteen datasets carrying one
false `settlement_id` each, it asserts 13 wrong compositions with no way to
signal doubt, while the resolver asserts 0 and reports 24 of 26 planted record
errors as findings. That sentence is supported by the false-attestation
measurements and by nothing else. It does **not** claim the absence cells work:
there the resolver attempts **1 of 24** settlement lines and fails the oracle.

### `AttestationDiscrepancy`: the false-alarm rate is zero

62 reported against 39 planted reads like a 40% false-alarm rate. It is not
one, and the difference is checked against the answer key's own
`reversal_debit` lines rather than argued:

| | count |
|---|---:|
| reported | **62** |
| planted and found | 37 |
| **true finding of another kind** — a bank debit revoking an earlier credit, corroborated in ground truth | **25** |
| **genuinely false** | **0** |
| planted but missed | 2 |

The 25 are a class of record error **the benchmark did not know to plant**: the
PSP says settled, the bank took the money back, and the two records contradict
each other. The two misses are `setl_igkKlAiC79ERI6`
(`datasets_v2/A40_B100_Cfifo`) and `setl_97AhUNQc71f0nz`
(`datasets_v2/A40_B100_Crandom`) — in both the bank blanked its own reference,
so the line falls to a tier that matches on amount from the recon rows, and the
recon rows are correct, so the corrupted scalar in `settlement_report.csv` is
never read.

---

## What the resolver actually claims

The outcome vocabulary is fixed by
[`resolver_contract/RESOLVER_CONTRACT.md`](resolver_contract/RESOLVER_CONTRACT.md),
which was committed **before any benchmark data existed** — the ordering is
visible in `git log` and is the point.

| outcome | what it means | may consume rows? |
|---|---|---|
| `Verified` | one party claimed a composition; that claim entailed a falsifiable prediction about an independent party's records; the prediction was checked and held | **yes, only this** |
| `AttestationDiscrepancy` | the sources disagree. Carries **no composition** — a discrepancy is a finding about the record, not a claim about which rows settled | no |
| `Reconstructed` | unattested, exactly one subset closes under **no objective filter**, and that subset closes no other unexplained credit in the window. Strictly weaker than `Verified` | no |
| `Ambiguous` | two or more compositions explain the credit. Carries the whole candidate set and its size. Has no `decomposition` attribute and never will | no |
| `Unresolved` | insufficient evidence, with a reason from an enum — `no_subset_closes` and `enumeration_truncated` are different findings | no |
| `ProvenUnmatched` | the ledger **entails** no bank credit exists — never captured, or netted to zero before eligibility. A claim | **G9** |
| `OpenBreak` | unplaced, classified, **aged**, routed to an owner with a close condition. Asserts nothing | never gated |

`Verified` is not "the composition is proven." No party outside the PSP ever
witnesses which rows formed a batch, so an outcome demanding independent
witness of composition could never occur. `Verified` claims the weaker thing
precisely, and every `Verified` carries `rival_closure_count` — how many other
subsets would have satisfied the same check — so a weakly corroborated answer
cannot be reported as if it were a strong one.

Three defects of the previous engine are **unrepresentable** in this vocabulary
rather than merely discouraged:

- an objective may only *rank* an already-complete candidate set, never filter
  one before uniqueness is tested (the old engine enumerated only subsets tying
  at its objective's optimum, so rival subsets were never constructed and no
  truncation flag could fire — two bank credits had three closing subsets each
  and were reported determinate);
- "rows common to every candidate" is an ambiguity *property* that is reported
  and never assigned (the old engine assigned from it, uncorroborated, 45 times);
- only `Verified` consumes pool rows, so a contested line cannot starve the
  next one (one reversal, two damaged bank lines, 50 misplaced rows).

---

## What is measured

An accounting, not a rate. `corpus/oracle.py` scores
`(resolver_output, ground_truth)` and shares no code with any resolver.

**Gated at zero:**

| gate | |
|---|---|
| G1 | `Verified` assignments that are wrong |
| G2 | `Verified` whose warrant lacks two independent parties |
| G3 | candidate sets that do not contain the truth |
| G4 | rows assigned through a path carrying no warrant |
| G6 | evidence whose declared provenance the corpus contradicts |
| **G7** | **abstention on a determined instance** (attested) |
| **G8** | **abstention on a reconstructible instance** (unattested) — uniqueness scoped to the simulator's pool, §46 |
| **G9** | a `ProvenUnmatched` row that actually settled |

G1–G6 are soundness gates and **every one of them is passed by a resolver that
answers nothing.** Worse, enumeration truncates first on the largest pools, so
the most adversarial data would produce the cleanest report. G7 and G8 are the
counterweight: they measure silence on instances the benchmark can *prove* have
exactly one answer. (G5 was withdrawn — see limitations.)

**Measured and reported, never gated:** the six-way outcome accounting; mean
**and max candidate set size**, always and unprompted, because without them
"declined fewer lines" and "enumerated more until the truth was in the set" are
indistinguishable and only the first is skill; `Unresolved` split by reason;
`AttestationDiscrepancy` detected against planted; and the rank-1 hit rate in
excess of chance, which measures whether the resolver's preferences agree with
the data generator's rule more often than luck.

**Deliberately not reported: "balance-identity violations."** Every candidate
satisfies `sum == target` by construction, so the residual is identically zero
and the check cannot fail. It was a headline metric in two earlier reports here.
Publishing an unfalsifiable number as evidence is the error this whole
repository exists to stop doing.

---

## The benchmark

`corpus/` is a family of seeded, deterministic datasets varying three axes:
pool size (10 → 60 rows eligible per batch), attestation coverage (100% → 0% →
absent), and the generator's own selection rule. Each ships its own isolated
answer key, its own hashes and its own generation report.

The measurement that motivates the whole design — closure uniqueness collapses
as the pool grows, counted with **no objective**:

| mean pool | bank credits with exactly one closing subset |
|---:|---:|
| 10 | 12/12 |
| 19 | 11/12 |
| 29 | 10/12 |
| 35 | 5/12 |
| 52 | 3/12 |

Above pool ~30 most bank credits have several arithmetically valid
explanations. Any engine that reports one answer per credit at those sizes is
reporting its tie-breaker, not its evidence.

Data quality is not asserted, it is searched for.
`corpus/leakage_audit.py` hunts for predicates that shortcut the task and is
validated by re-discovering four known defects in the frozen dataset unaided.
It rejected this corpus four times across five regenerations. `corpus/
triviality_check.py` asks the complementary question — *does a trivial
predicate solve the task outright?* — and its answer is permanent output, not
a footnote. See limitations, immediately below, for why that check exists.

---

## Limitations

Stated here rather than left for a reader to find. Every one is measured.

**A fifteen-line `GROUP BY` scores 168/168 on the original 14 datasets.**
`settlement_id` is populated on every settled row and the original corpus never
plants a false one, so a resolver that simply trusts the PSP is perfectly
calibrated there and the benchmark cannot distinguish it from a sound one. Axis
A does not measure difficulty on those datasets: the difficulty binds only a
solver that has withheld `settlement_id` from itself. This was found by
finally running a baseline *dumber* than the one under attack — 1,346 lines of
leak audit had never asked the question. It is the most important thing the
benchmark discovered about itself, and it is why the PSP-absence and
false-attestation datasets exist. On the original 14, **the naive baseline
wins outright.**

**The resolver fails the oracle on the two PSP-absence datasets**, on gates G8
(it stays silent on 15 of 18 bank lines that have exactly one explanation
**over the pool the simulator drew from** — 3 to 42 rows — while the resolver
searches a pool it derived itself, 7 to 414 rows, up to **14× larger**;
uniqueness in 2¹⁵ is not evidence of uniqueness in 2²¹³, so the gate compares
two frames and the earlier phrasing "the benchmark proves have exactly one
explanation" was false as written, `DECISIONS.md` §46) and G3 (the truth is not inside the candidate sets it managed to
build). The cause is structural and was written down before the run: only
`Verified` may consume rows, `Verified` needs an attestation, and there is no
attestation there — so the eligible pool grows monotonically across the window,
from 8 rows at the first credit to 265 at the last, and closure stops being
unique. It is the only system that runs on those datasets at all, and it
declines most of the work. Both facts are the result.

**"0 wrong answers" used to mean "0 wrong `Verified`" and nothing more.** A
second outcome, `CorrectlyUnmatched`, also asserted something — that a row
correctly had no bank credit — and no gate looked at it. Enumerated over all
30 datasets it was **45.7% accurate across 4,994 claims**, and **2,469 of the
rows it said had no bank credit had settled**. One of its six reasons,
`rolled_forward`, was right **17 times out of 2,397**; it was defined in the
contract as *"eligible, not selected"* — a residual — four lines below a
requirement that every reason be derived. It is now split into
`ProvenUnmatched` (699 rows, gated at zero by G9, **0 failures**) and
`OpenBreak` (4,295 rows, which assert nothing). Full audit:
[`investigation/DERIVED_BRANCH_AUDIT.md`](investigation/DERIVED_BRANCH_AUDIT.md).

**The proven rate is 14%, and that is the intended shape.** A small set with a
genuine entailment claim behind a zero-tolerance gate, plus a large classified
and aged break queue, is what production reconciliation ships. A system
claiming to have positively explained all 4,994 rows would be the less
credible artefact — that is precisely what the old outcome claimed.

**1,469 `OpenBreak` rows are `unexplained`**, 758 of them at the two
PSP-absence datasets, where no attestation exists so no causing line can be
named and the resolver cannot say why it failed. The category is reported
rather than absorbed into a neighbouring one, because absorbing it is exactly
how `rolled_forward` came to exist.

<!-- MEASURED-LIMITATIONS:START -->
**87% of `Verified` are non-decisive** — 239 of 275. The composition claim was corroborated by a consequence a rival composition would also have satisfied. The contract requires that number to be reported precisely so the `Verified` count cannot be quoted without it.

**Wrong answers, by outcome type and with its population.** `Verified` wrong: **0** of 275 (gate G1). `ProvenUnmatched` rows that in fact settled: **0** (gate G9). `Reconstructed` wrong: **0** of 1. That last denominator is 1 — `Reconstructed` occurs almost never in this corpus, so it is reported as a **count and not a rate**; neither this figure nor the previous run's “1 wrong of 2” says anything about accuracy.
<!-- MEASURED-LIMITATIONS:END -->

**A theorem in the contract was false, and a gate enforced it.** §6.3 asserted
that at 0% attestation coverage no composition claim exists, so `Verified` must
be empty, and oracle gate G5 rejected any `Verified` there. Measured on the
data: all 12 settlement-report rows present, all 12 reported amounts matching a
bank credit, 255 of 314 recon rows carrying `settlement_id`. The claim exists
and `Verified` is achievable — **G5 would have rejected correct answers.** §6.3
and G5 are withdrawn and dated, with the original text left visible. The
document written to prevent unsupported claims made one.

**The GST leg is not earned.** All axes are settlement-side. The 2B file has no
volume of ITC decisions, no partially-filed-supplier population, no IRN timing
distribution. The three statutory findings it produces are each a
single-column filter. **Do not read any GST claim here as demonstrated.**

**There is no wrong-*bank*-side class.** The benchmark plants attestations that
are wrong. It never plants a case where the two sources contradict and the
truth is on the *bank* side — a bank splitting one settlement into two credits,
say. So "two independent parties agree" is never tested at the one point where
the direction of the disagreement matters. This is the largest remaining gap.

**Other named gaps.** The foreign-credit class is a rare-event class as built —
amounts are drawn independently of the ledger, so a subset almost never nets to
them, and the frozen engine adopted 1 of 112. 14 of 60 grid cells are run; B × C
is untested. `Reconstructed`'s cross-line exclusivity is necessary, not
sufficient: a credit that has not posted yet cannot be excluded against.

**Three defects in the frozen engine are documented and unpatched**, on purpose
— it is the baseline the benchmark has to be able to fail. See
[`investigation/DEFECT_REPORT.md`](investigation/DEFECT_REPORT.md).

---

## Layout

```
resolver_contract/   the outcome vocabulary. Interface only, no algorithm.
                     Committed before any benchmark data existed.
resolver/            the resolver. Imports the contract and nothing else.
corpus/              the benchmark: generator, datasets, leak audit,
                     triviality check, oracle, baselines
engine/              the frozen data generator and its settlement spec
matching/            the frozen 4-stage cascade (the previous engine)
eval/, holdout/,     the earlier evaluation of the frozen engine, including
scale/               the held-out run that produced the 50 wrong answers
investigation/       the defect report
DECISIONS.md         numbered, append-only; every entry carries the
                     alternatives it rejected and why
CHECKPOINT.md        the current state, written against the artefacts on disk
```

The dependency direction is one-way and load-bearing: `engine/` generates the
data and the isolated answer key, `resolver/` and `matching/` never read the
key, and only `eval/` and `corpus/oracle.py` are permitted to. It is enforced
by tests that scan imports and file access by AST, not by convention.

---

## Ordering is the evidence

Each of these is one commit, and `git log` shows them in this order:

```
resolver contract      before any benchmark data existed
benchmark seeds        before any data was generated
datasets               at those seeds, never reselected
baseline prediction    before the old engine was run once
baseline results       the run
new seeds              before the absence and false-attestation data existed
the resolver           before the oracle scored it once
oracle results         the run
```

A benchmark built after the contract cannot be shaped to an implementation. A
prediction committed before a run cannot be edited to match it. A resolver
frozen before scoring cannot be tuned to the scorer. None of that requires
trusting anyone; it requires reading `git log`.
