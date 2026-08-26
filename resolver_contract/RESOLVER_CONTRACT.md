# RESOLVER_CONTRACT.md

**Status:** normative. `resolver_contract/types.py` implements this document
and nothing else. Interface and semantics only — no algorithm, no solver, no
matching logic.

**Committed before any corpus data exists.** That ordering is the evidence and
is verifiable from `git log`: the commit containing this contract precedes the
commit containing any dataset. A corpus built after the contract cannot be
shaped to an implementation, and a resolver built after the corpus cannot
redefine the outcome it is scored on. Same protocol as `holdout/SEED.txt`
(`DECISIONS.md` §17), for the same reason.

---

## 0. What this replaces, and why

The previous engine reported **96.55% match rate and 1.000 precision** on the
frozen primary dataset and then produced **50 confident wrong answers** on
held-out data. Root-cause analysis found three engine defects
(`investigation/DEFECT_REPORT.md`) and an audit of the data found seven more,
four of which mean the primary dataset was *structurally incapable* of
exposing the engine defects (`corpus/CORPUS_SPEC.md` §1).

The common shape of all ten is one sentence:

> **A claim was made that no evidence supported, and the type system had no
> way to notice.**

`Determinate` meant "unique among subsets maximising applied debits" and was
read as "this is the answer". `BalanceProof` was called *"why a resolution is
believed"* and proved only that the selected rows sum to the selected total —
a quantity that is identically zero by CP-SAT construction and therefore
cannot fail. `Ambiguous.certain_rows` assigned rows through a property named
as if it were an observation. In each case, the failure was not that a check
was skipped: it was that the vocabulary made an unsupported claim *sayable*.

This contract makes it unsayable.

---

## 1. The one rule

> **An assignment is a claim about the world. Every claim carries a warrant,
> and the warrant states what evidence supports it, which independent parties
> that evidence comes from, and what contradicts it.**

There is no constructor in `types.py` that produces an assignment without one.
That is not a coding convention; `Warrant` is a required positional field on
every outcome, and every outcome that carries an assignment validates its
warrant in `__post_init__`.

---

## 2. Binding rules

These are the rules a resolver is judged against. Each is mechanically checked
either by `types.py` at construction or by `corpus/oracle.py` at scoring, and
each names the defect it exists to prevent.

### 2.1 No objective may filter candidates before uniqueness is tested

An objective may only **rank an already-complete candidate set**, and wherever
one appears it must be labelled a modelling assumption.

*Mechanism:* `CandidateSet.__post_init__` raises if any `RankingAnnotation`
has `applied_after_enumeration=False`. `RankingAnnotation` raises if
`modelling_assumption` is blank.

*The defect.* `enumerate_decompositions` maximised applied debits and then
enumerated only solutions achieving that optimum. Rival closing subsets were
never constructed, so they could never surface as a tie and **no truncation
flag was raised, because nothing was truncated**. Two primary bank credits had
three closing subsets each and were reported `Determinate`. Worse, the
objective is `SETTLEMENT_SPEC.md` §1.4 — the same rule that generated the
data. Solver and generator shared a premise, and no amount of column
withholding makes a shared assumption into independent evidence.

### 2.2 Independence is over PARTIES, not over evidence kinds

Two evidence kinds are two facts. They are two *sources* only if two different
parties produced them.

*Mechanism:* `Evidence.derived_from` names source systems; `SOURCE_PARTY`
collapses systems to parties; `IndependenceDetermination.independent_count`
counts parties. `Warrant.__post_init__` recomputes the determination from the
evidence and raises if a resolver declared something the evidence does not
support.

*The defect.* On the frozen dataset
`settlement_utr == str(settled_at) + settlement_id[-6:]` on **11 of 11**
batches, and the bank narration embeds that UTR verbatim on **9 of 12** lines.
The settlement id and the bank UTR look like two sources and are one. Any
architecture treating attestation+bank agreement as corroboration is reasoning
in a circle on that data. A PSP's recon feed and a PSP's settlement report are
likewise one party, however many files they arrive in.

### 2.3 Arithmetic closure over attestation-named rows is a consistency check on
that attestation, not independent corroboration of it

*Mechanism:* `arithmetic_closure_over()` requires the caller to name the
sources of the rows it closed over, and the resulting evidence carries exactly
those sources. Closure over PSP-named rows therefore adds no party.

### 2.4 Only `Verified` consumes. Contested rows stay in the pool

*Mechanism:* `may_consume(outcome)` is `isinstance(outcome, Verified)` and is
the only consumption predicate the contract defines.

*The defect.* `stage3_solver.run` advanced the pool on an uncorroborated
`Determinate` via an unguarded `elif`. It never executed on the primary set —
every primary bank line is attested — and on its first execution it consumed
50 rows into the wrong bank line, which then starved the *correct* line.
**One reversal damaged two bank lines.** A branch that cannot execute on the
only dataset in the repo is untested by construction, and a 268-test suite
passing said nothing about it.

### 2.5 "Rows common to all candidates" is an ambiguity PROPERTY, never an
assignment

*Mechanism:* `Ambiguous.common_rows` exists, is documented as a report field,
and `Ambiguous.assigned_rows` returns `()` unconditionally. There is no path
from an `Ambiguous` to a row assignment.

*The defect.* `Ambiguous.certain_rows` was consumed as an assignment. It is a
third confident-assignment path that any `Determinate`-scoped guard misses,
and it produced 3 wrong placements that survived the best single fix in the
remediation sweep.

### 2.6 A confident answer on an ambiguous batch is unrepresentable

*Mechanism:* `Ambiguous` has no `decomposition`, and `__getattr__` raises
`UnrepresentableClaim` — not `AttributeError` — for `decomposition`,
`composition`, `best`, `chosen` and `answer`, so the failure names the design
intent instead of reading like a typo.

---

## 3. Evidence

### 3.1 The kinds

| kind | party | attests to | what it does NOT license |
|---|---|---|---|
| `ATTESTED_SETTLEMENT_ID` | psp | composition | that the PSP is right |
| `BANK_REFERENCE` | bank | **existence** | anything about composition |
| `BANK_VALUE_DATE` | bank | existence | anything about composition |
| `ATTESTED_COMPOSITION_CLOSES` | inherits | **consequence** | that no rival composition closes too |
| `ARITHMETIC_CLOSURE` | inherits | consequence | anything, when the rows were chosen to make it true |
| `UNIQUE_CLOSURE_UNFILTERED` | inherits | composition | that the subset belongs to *this* credit (§4.3) |
| `CROSS_LINE_EXCLUSIVITY` | inherits | composition | that a later line will not revoke it |
| `ERP_IDENTIFIER` | merchant | **row existence** | batch membership |
| `GST_DOCUMENT` | tax authority | row existence | batch membership |
| `DISPUTE_RECORD_LINK` | issuer | row existence | batch membership |

`EVIDENCE_SEMANTICS` is a fixed table in `types.py`. A resolver does not get to
declare what its evidence attests to — that would make the oracle check the
resolver's rule against the resolver's own self-report, which is a tautology.
The resolver declares only `derived_from`, and the oracle validates *that*
against the corpus provenance graph (§7).

### 3.2 Existence is not composition, and this is the distinction the old
engine did not draw

A bank reference tells you ₹99,329.23 arrived on 2026-07-15 under reference
`RATN26189004417`. It says nothing about which of the 21 eligible ledger rows
composed it. **A bank knows what it paid; it never knows what it paid *for*.**
Letting existence evidence corroborate a composition claim certifies a
composition on evidence that cannot bear on it.

The same holds one level down for `ERP_IDENTIFIER`. An `order_id` tied to an
invoice proves the row is a real sale. No ERP file contains a settlement
reference, so it carries zero batch-membership information.

### 3.3 So what does `Verified` actually claim?

Not "the composition is proven". No party outside the PSP ever witnesses which
rows formed a batch, so a contract that demanded independent witness of
composition would define an outcome that can never occur.

`Verified` claims this, and only this:

> **One party made a composition claim. That claim entailed a falsifiable
> prediction about an independent party's records. The prediction was checked
> against those records and it held.**

The prediction is "the rows I named sum to what you actually paid." It *could*
have failed — and when it does, the contract has a name for that
(`AttestationDiscrepancy`, §4.2), which is the whole reason the corroboration
is worth anything.

**How much it is worth depends on how discriminating the prediction was.**
A prediction that 400 rival compositions also satisfy is weak corroboration of
*this* one. So `Verified.rival_closure_count` is **mandatory** — the number of
subsets of the pool that close to the same amount under no objective filter —
and `corroboration_is_decisive` is true only when it is 1. The oracle reports
the distribution per axis cell. An unmeasured strength is an unstated
weakness, and `rival_closure_count=0` is rejected at construction because 0
means it was never measured.

Decisiveness is **reported, not required**. Requiring it would make `Verified`
unreachable on exactly the large pools the corpus exists to explore, which
would convert an honest weakness into a hidden abstention.

---

## 4. The outcomes

### 4.1 `Verified`

Two independent parties, one composition claim, one confirmed consequence, no
contradiction. **The only outcome that may consume.** The only outcome whose
wrongness is a build failure rather than a measurement.

Construction fails unless the warrant carries (a) evidence attesting to
composition, (b) evidence attesting to a consequence, (c) two independent
parties, (d) no contradictions, and (e) a `rival_closure_count ≥ 1`.

### 4.2 `AttestationDiscrepancy`

The sources disagree. **The highest-value output this contract defines**, and
the one the old engine structurally could not produce: with one effective
source there was nothing to disagree with, and its only vocabulary for
"something is off" was `Unresolved`, which says *"I could not explain this"*
rather than *"the record is wrong"*. In production that difference is the
difference between a queue item and a ticket to the PSP.

Carries **no composition**. A discrepancy is a finding about the record, not a
claim about which rows settled.

### 4.3 `Reconstructed`

Unattested; exactly one subset closes under no objective filter; **and** that
subset closes no other unexplained credit in the window.

The cross-line requirement is not decoration, and this is the correction that
matters most in this document. At all three bank lines that produced the 50
wrong rows, the pool admitted **exactly one** closing subset — `OPTIMAL`,
untruncated, no tie to miss. Per-credit uniqueness held perfectly and the
answer was still wrong, because those rows were the true composition of a
*later* credit. **Uniqueness is a per-credit predicate answering a
cross-credit question.** A contract whose reconstruction outcome required only
uniqueness would reproduce the 50-row failure verbatim, and the warrant would
make it look *more* credible.

*Named limitation, disclosed rather than discovered later.* Cross-line
exclusivity is a necessary condition, not a sufficient one. A credit that has
not posted yet, or falls outside the window, cannot be excluded against. The
contract requires the check over the window the resolver can see and requires
the window to be stated on the evidence's `detail`. `DECISIONS.md` §2 records
that the global formulation was attempted and returned UNKNOWN at 60s on 1,347
booleans, so a resolver satisfying this cheaply is not a solved problem — it
is the open work this contract deliberately points at.

`Reconstructed` is **strictly weaker than `Verified`** and is named so the two
cannot be confused at a call site or in a report. It **does not consume**.

### 4.4 `Ambiguous`

Two or more compositions explain the credit. Carries the complete candidate
set and its size; when enumeration stopped early the set is an explicit
**sample** and the line is *more* ambiguous than its length suggests, never
less. No assignment, no `decomposition`, ever.

### 4.5 `Unresolved`

Insufficient evidence. Carries a reason from `UnresolvedReason` — an **enum,
not free text** — because `no_subset_closes` and `enumeration_truncated` are
completely different statements and the second is the one that would otherwise
let the hardest cells of the corpus produce the cleanest numbers (§6.1).

Carries `partial_candidates` when enumeration truncated. A resolver that
discards a truncated set has destroyed the evidence of its own miss, and the
oracle checks whether the truth was inside what the resolver actually built.

### 4.6 SUPERSEDED (2026-08-25) by §4.7 — `CorrectlyUnmatched`

**Superseded, original text retained below.** The outcome conflated a positive
claim with an absence of evidence and was measured at 45.7% accuracy over
4,994 claims. See `investigation/DERIVED_BRANCH_AUDIT.md` and §4.7.

### 4.6 (original text, superseded) `CorrectlyUnmatched`

Rows that correctly have no bank credit, with a **derived** reason from
`UnmatchedReason`: netted out, rolled forward, not yet eligible, dispute held,
debit deferred, failed at gateway. The oracle scores the *reason*, not the
classification. "Unmatched, and I have a label for it" is not the claim.

### 4.7 Amendment (2026-08-25): `ProvenUnmatched` and `OpenBreak`

**Added after the corpus and the first resolver were built, and dated rather
than folded in**, for the same reason §6.4 is dated: this document's claim on
being trustworthy is that it was written before the data it judges.

#### Why §4.6 had to be replaced

`CorrectlyUnmatched` asserted one thing and was used for two. Measured over
all 30 datasets — 4,994 claims, full enumeration, no sampling:

| branch | right | wrong reason | **row actually settled** | total | accuracy |
|---|---:|---:|---:|---:|---:|
| positively derived | 1,828 | 36 | 8 | 1,872 | 97.6% |
| residual fallthrough | 455 | 206 | **2,461** | 3,122 | **14.6%** |
| all | 2,283 | 242 | 2,469 | 4,994 | 45.7% |

`ROLLED_FORWARD` — defined in `types.py` as *"eligible, not selected"*, a
residual by construction — was right **17 times out of 2,397**. The contract
demanded that every reason be "DERIVED, not assumed" and in the same file
specified a bucket that cannot derive.

Two different claims were wearing one type:

* **(a)** *the ledger entails no bank credit exists for this row* — a positive
  claim, derivable from row state alone;
* **(b)** *I did not place this row* — an absence of evidence, reported as if
  it were (a).

#### The gate is ENTAILMENT, not accuracy

Correcting the derivations to transcribe `engine/simulator.py` exactly makes
the reasons **more accurate** (36 wrong → 10) and the soundness gate
**dramatically worse** (8 rows-that-settled → 64), because a corrected
`dispute_held` promotes 142 rows out of the residual, where they assert
nothing, into a derived branch, where they become positive false claims.

A more accurate classifier is a more dangerous one here. Accuracy is not the
property this outcome needs. **Admission to `ProvenUnmatched` is by
entailment: there must exist a derivation from merchant-visible ledger state
to "no bank credit exists", and a reason that scores well without one does not
qualify.**

#### 4.7.1 `ProvenUnmatched`

> **`ProvenUnmatched` asserts that the merchant-visible ledger alone entails
> that this row's money never reached the bank — because it was never
> captured, or because it and its refunds annihilate to zero before it ever
> became eligible — and it makes no claim about any row whose settlement is
> merely deferred, withheld, or unknown.**

Weaker than "the ledger entails no bank credit exists", deliberately, and for
the reason §3.3 gives for `Verified`: name the limit rather than define an
unreachable ideal.

Exactly two reasons qualify, and the list is closed by measurement:

| `ProvenUnmatchedReason` | derivation | measured counterexamples |
|---|---|---:|
| `NOT_CAPTURED` | `credit == 0`; a payment never captured never became money | **0** of 215 |
| `NETTED_OUT` | Σ refund amounts `==` the payment's **gross** amount **and** every refund created at or before `eligible_at`. `SETTLEMENT_SPEC.md` §3; transcribed from `engine/simulator.py` | **0** of 484 |

`NETTED_OUT` requires *exact* equality against the **gross** amount and a
timing test on **every** refund. The first resolver used `>=` against the
fee-net `credit` with no timing test, and each of those three divergences
alone produced false claims.

**Gated by G9 at zero tolerance.** A `ProvenUnmatched` row that settled is a
gate failure, not a measured statistic. Until this amendment, "0 wrong
answers" in every report meant **"0 wrong `Verified`"** only; a second outcome
type was wrong thousands of times and no gate looked at it.

#### 4.7.2 `OpenBreak`

**An `OpenBreak` asserts nothing and is therefore never gated on
correctness.** It records that an item is unreconciled, why the resolver
thinks so, how long it has been open, and what would close it. A row the
resolver simply failed to place is an `OpenBreak`, always — there is no path
by which failing to place a row becomes evidence about the row.

This follows production reconciliation practice, where an unmatched item is a
*break* carried forward with a classified reason and an age until it is
resolved, not a verdict. Oracle-vendor and PeopleSoft reconciliation models
have no terminal "correctly unmatched" state at all: an item is reconciled, or
it is an exception awaiting resolution.

| `BreakReason` | means | owner | closes when |
|---|---|---|---|
| `MISSING_SOURCE` | an expected artefact is absent — no settlement report, no bank line for the period | data ops | the missing artefact arrives |
| `TIMING_DIFFERENCE` | activity falls across the reporting boundary; not yet eligible, rolled forward | none — carry forward | the item settles in a later window |
| `MAPPING_ISSUE` | the row does not fit the expected linkage — unjoinable adjustment, no ERP order | integrations | a linkage is established |
| `UNEXPECTED_CHANGE` | dispute hold, reversal, revocation | disputes ops | the hold or reversal resolves |
| `TRUE_ERROR` | duplicate, omission, or wrong amount | finance | the correcting entry posts |
| `UPSTREAM_UNRESOLVED` | this row's disposition depends on a **bank line** whose own outcome is unsettled | whoever owns the causing finding | the causing line becomes `Verified` or `ProvenUnmatched` — at which point every row clustered under it is re-evaluated **together** |
| `UNEXPLAINED` | the resolver could not classify it | investigation | — |

`UNEXPLAINED` **is a real, reported category and must never be eliminated by
widening the others.** A high `UNEXPLAINED` count is an honest finding. The
whole failure §4.6 records is what happens when a residual is given a name
that sounds like a derivation.

`UPSTREAM_UNRESOLVED` is the sixth reason the standard five do not cover.
These rows are not `MISSING_SOURCE` (the source is present and legible), not
`TIMING_DIFFERENCE` (they are inside the window), not `MAPPING_ISSUE` (they
map fine), not `UNEXPECTED_CHANGE` (nothing about the row changed), and not
`TRUE_ERROR` (no error has been established). Their batch membership is
unknown **because an upstream finding about a different object is
unresolved**. Measured: 2,461 rows cluster under 83 causing bank lines, mean
29.7 rows per cause — a 30× reduction in queue length. Forcing them into
`TRUE_ERROR` would assert an error nobody has demonstrated; forcing them into
`UNEXPLAINED` would hide the one thing actually known about them.

#### 4.7.3 Aging

Every `OpenBreak` carries `age_days` from the date the item first became
reconcilable — `eligible_at` for a payment, `created_at` otherwise — to the
reporting horizon, and the period in which it first appeared. Reported in the
standard buckets **0–30 / 31–60 / 61–90 / 90+**. An item aged past a prior
period is red-flagged.

Aging is what makes "rolled forward" a *tracked state* rather than a terminal
verdict, and its absence is what let §4.6's residual look like an answer.

#### 4.7.4 Reasons that score well and still do not qualify

Measured, corrected predicates, full enumeration:

| reason | rows | **settled** | verdict |
|---|---:|---:|---|
| `not_yet_eligible` | 952 | **0** | entailed **for this window only** → `OpenBreak / TIMING_DIFFERENCE`, flagged `provable_within_window` |
| `dispute_held` | 345 | **64** | **not entailed** → `OpenBreak / UNEXPECTED_CHANGE` |

`not_yet_eligible` is sound by a *provable* margin, not by luck: the
resolver's horizon is the last bank `value_date`, the true horizon is the last
batch time, and the former is always the later of the two, so the test is
strictly stronger and can miss but never false-positive. It is nonetheless an
`OpenBreak`, because `ProvenUnmatched` means *no bank credit exists* and a
not-yet-eligible row's bank credit exists next Tuesday. Gating a temporary
state as a permanent proof is how the distinction rots. The strength of the
evidence is preserved in a flag, not in the outcome type.

`dispute_held` fails on phase semantics, not on implementation quality
(`SETTLEMENT_SPEC.md` §6.1): `retrieval` and `fraud` *withhold* funds, while
`chargeback` *claws back after settlement*. All 31 lost chargebacks in the
corpus settled and were then reversed by a debit. A clawback is a later debit,
not a non-settlement.

#### 4.7.5 `attested_row_ids` is defined here, having never been defined

§4.2 named no field. The implementation gave one field three meanings across
five call sites, and real cause-pointer coverage was 701 of 1,765 rows
(39.7%). Two distinct questions were sharing one answer:

* **`Contradiction.row_ids`** — the rows *implicated in the contradiction*.
  The offending subset, and only it.
* **`AttestationDiscrepancy.attested_row_ids`** — **every row the PSP attested
  to this bank line**, whether or not it is implicated. Populated whenever an
  attestation exists, including on a reversed credit, where the settlement
  report names the rows even though the money came back.

The `OpenBreak` cause pointer reads the second. A discrepancy that names only
its offending rows under-points: `temporal_impossibility` named 13 rows out of
294 in the affected batches, and the other 281 are equally blocked.

---

## 5. The reported output shape

An accounting, not a rate:

```
Verified                  n   (of which non-decisive: n)
AttestationDiscrepancy    n   by contradiction kind
Reconstructed             n
Ambiguous                 n   (of which incomplete enumerations: n)
Unresolved                n   by reason
ProvenUnmatched           n   by reason      <- gated at zero by G9
OpenBreak                 n   by reason, and by age bucket 0-30/31-60/61-90/90+
                              (of which clustered under a causing line: n
                               across k distinct causes)
mean candidate set size   x.xx        <- always, unprompted
max candidate set size    n
```

**`OpenBreak` is reported by age as well as by reason** (§4.7.3). A break
count without an age distribution cannot distinguish a healthy queue from one
carrying the same items across three periods.

**`ProvenUnmatched` and `OpenBreak` are never summed into one figure.** One
asserts, the other does not, and a total over both would recreate exactly the
conflation §4.7 exists to undo.

**Mean candidate set size is reported always and unprompted.** Without it,
"declined fewer lines" and "enumerated more candidates until the truth was
somewhere in the set" are indistinguishable, and only the first is skill.

**"0 wrong answers" means what it is scoped to and nothing more.** Before the
§4.7 amendment every such claim in this repository meant *"0 wrong
`Verified`"*, while `CorrectlyUnmatched` — an outcome that also asserted
something — was wrong 2,469 times unexamined. Any soundness claim must now
name the outcomes it covers, and G9 covers `ProvenUnmatched`.

**Deliberately NOT reported: "balance-identity violations".** Task 4 of the
defect report proved it structurally incapable of being non-zero — every
candidate satisfies `sum == target` by CP-SAT construction, so the residual is
identically zero, and `Determinate.__post_init__` cannot fire from any code
path in the repository. Publishing an unfalsifiable quantity as a headline
metric is the same error class as everything else on this page. It is replaced
by three checks that *can* fail: attestation-composition agreement, bank
reference independence, and closure uniqueness measured without an objective.

---

## 6. Abstention is not free

### 6.1 The determined subpopulation

Every hard guarantee in §2 is a **soundness** guarantee, and every soundness
guarantee is satisfied by a resolver that returns `Unresolved` to everything:
no wrong `Verified`, no uncorroborated warrant, no ambiguity missing its
truth, no unwarranted assignment — all zero, all vacuous. Worse, enumeration
truncates first on the largest pools, so **the most adversarial cells of the
corpus would produce the cleanest numbers in the report.** A contract with
only soundness gates is a certificate of abstention.

So the contract defines the subpopulation on which silence is a defect.

> A bank line is a **`DeterminedInstance`** when, under an enumerator
> independent of any resolver and carrying **no objective**:
>
> 1. exactly one subset of the pool closes to the credit, and
> 2. that subset closes no other unexplained credit in the window, and
> 3. the attestation is present and agrees with it,
>
> and the enumeration that established (1) was **complete**, not capped.

On these instances `Unresolved` and `Ambiguous` are **failures**, gated at
zero by `ResolverOutput.abstention_failures`. `DeterminedInstance.__post_init__`
refuses to construct one from a capped enumeration, so the corpus cannot
quietly widen the subpopulation to make a resolver look better.

This gate cannot be passed by silence, because silence is what it measures.

### 6.2 The premise-sharing statistic

Axis C of the corpus varies the generator's selection rule across
`max_under_cap` / `fifo_under_cap` / `random_valid`. The intent is that a
sound resolver scores flat across all three, and degradation on one means it
shares an assumption with the generator.

**Stated that way the test is unfalsifiable.** At pool 40–60 under
`random_valid`, closure is massively non-unique, so a *sound* resolver returns
`Ambiguous` almost everywhere and every outcome-level metric is flat under
both hypotheses. Flat-at-the-floor proves nothing.

The falsifiable form measures the **ranking**, which exists on every instance
including the ones correctly declined:

> **Rank-1 hit rate in excess of chance, over multi-closure instances.**
> Restrict to lines where the independent enumerator finds *k ≥ 2* closing
> subsets and the enumeration was complete. Report
> `P(candidate_set.rank_one == truth) − mean(1/k)`, per selection rule.

Under the null — no shared premise — this is 0 for all three rules by
construction. Under premise sharing it is strongly positive for
`max_under_cap`, near zero for `random_valid`, and `fifo_under_cap` says
whether the sharing is specific to reading (B) or general.

Two conditions, both binding on the corpus rather than the resolver:

* the `1/k` baseline is valid only if `random_valid` samples **uniformly**
  among closing subsets. The corpus states which sampler produced each batch
  and never claims uniformity for a sampler that does not have it
  (`corpus/CORPUS_SPEC.md` §4);
* *k* comes from an enumerator independent of the resolver's, with a cap far
  above any resolver's. Instances that hit the cap are **excluded from the
  statistic and reported as excluded**, never silently dropped.

`CandidateSet.ranked` and `CandidateSet.rank_one` exist for this and only
this. Reading `rank_one` is not reading an answer — it is reading a
preference, which is exactly the thing under test.

### 6.4 Amendment (2026-08-24): the same hole, one axis over

**This section was added after corpus generation began, and it is dated rather
than folded in**, because this document's entire claim on being trustworthy is
that it was written before the data.

Measured on the generated corpus:

| axis point | `DeterminedInstance` | lines with unique complete closure |
|---|---:|---:|
| `A20_B100_Cmax` | 10 | 11 (all attested) |
| `A20_B75_Cmax` | 8 | 12 (3 unattested) |
| `A20_B50_Cmax` | 5 | 11 (5 unattested) |
| `A20_B0_Cmax` | **0** | 11 (**11 unattested**) |

At 0% coverage **every gate was vacuous.** §6.3's theorem forces
`|Verified| = 0`, so the wrong-`Verified` and independence gates had nothing to
check; and `DeterminedInstance` requires the attestation, so §6.1's gate had an
**empty subpopulation**. A resolver returning `Unresolved` to everything scored
perfectly on the one axis point that is purely about reconstruction — and it is
the cell where the branch that produced all 50 wrong answers actually lives.

That is §6.1's hole reopened one axis over, and §6.3 predicting the cell would
be empty is what disguised it: the prediction came true and nothing was
learned.

So `ReconstructibleInstance` is defined: a bank line that is **unattested** and
still has exactly one closing subset under a complete objective-free
enumeration, **and** whose subset closes no other unexplained credit in the
window. `Reconstructed` is achievable there, so `Unresolved` and `Ambiguous`
are failures, gated at zero.

**What the amendment does not change.** No outcome semantics, no existing gate,
no generated dataset. It is derived from closure registers already present in
every ground-truth key, so nothing was regenerated to make it true — which is
what keeps it an addition rather than a re-cut of the benchmark after seeing
results.

---

### 6.3 WITHDRAWN (2026-08-24): the theorem is false on the corpus's own data

**This section stated a theorem, gated on it, and the theorem is wrong. It is
withdrawn rather than edited, and the original claim is left visible below so
the record shows what was asserted.**

*What it claimed:* only the PSP attests to composition, so with no attestation
there is no composition claim, and therefore `|Verified| = 0` necessarily at 0%
coverage.

*What is actually true, measured on `corpus/datasets/A20_B0_Cmax/`:*

| | |
|---|---|
| `settlement_report.csv` rows present | **12 of 12**, each with a `settlement_id` |
| `reported_amount` matching a bank credit verbatim | **12 of 12** |
| recon rows carrying `settlement_id` | **255 of 314** |

**Axis B varies the bank-line → batch *reference*, never the composition
claim.** `settlement_id` is at 100% in every cell of the corpus. So a
composition claim exists at "0% coverage", it entails a falsifiable prediction
about the bank's amount, and that prediction can be checked — which is exactly
§3.3's definition. `Verified` is fully achievable there.

**The gate built on it was worse than the error.** `corpus/oracle.py` G5 flagged
any `Verified` at 0% coverage as a violation, so it would have rejected correct
answers. G5 is withdrawn with this section.

**And §6.4's amendment rests on the same misdiagnosis.** `ReconstructibleInstance`
was introduced because the B0 cell was judged "purely about reconstruction"
with an empty `Verified` set. It is not — the attestation is present there in
two artefacts. The amendment is *retained* because its own justification stands
on its own (a line with unique, complete, cross-line-exclusive closure and no
usable bank reference is reconstructible, and abstaining on it is a defect), but
the reasoning that led to it was wrong and that is recorded here rather than
left to look prescient.

**Why this is the sharpest failure in this document.** §0 names the defect this
contract exists to prevent: *"a claim was made that no evidence supported, and
the type system had no way to notice."* §6.3 asserted a claim a priori,
described it as *"stated in advance, as a prediction of the contract"*, and
gated on it without ever measuring it. The document written to prevent that
error committed it.

---

### 6.3 (original text, withdrawn) Theorem: at 0% attestation coverage, `Verified` is empty

From §3.2 and §4.1: `Verified` requires evidence attesting to composition from
a party independent of the party confirming the consequence. Only the PSP
attests to composition. Therefore with no attestation there is no composition
claim, and **`|Verified| = 0` necessarily.**

This is stated **in advance, as a prediction of the contract**, and the oracle
gates on it. Otherwise the 0% cell comes out empty and nothing has been
learned that was not assumed.

It follows that the 0% cell measures **abstention discipline, not resolution**
— which is precisely why §6.1's gate is mandatory rather than optional, since
abstention is otherwise free there.

It also follows that axis B does its real work at 75% and 50%. That is a
limitation of the axis and is recorded as one in `corpus/CORPUS_SPEC.md` §8,
not smoothed over.

---

## 7. What the oracle validates that the resolver cannot self-certify

A resolver declares `Evidence.derived_from`. If the oracle accepted that
declaration, the independence gate would check the resolver's rule against the
resolver's own self-report.

So the corpus ships a **provenance graph**: for every artefact and every field,
which source system minted it and from which random draw. Two evidence kinds
are independent **iff they descend from disjoint draws**. The oracle validates
every `derived_from` against that graph and reports mismatches as contract
violations attributable to the resolver.

This check is only possible because we build the corpus. It is the strongest
single argument for building one.

---

## 8. Rejected alternatives

**Rejected: a confidence score in [0,1] instead of typed outcomes.** A float
makes every wrong answer a threshold-tuning exercise and makes the *kind* of
claim invisible — 0.9 cannot distinguish "two parties agree" from "one party
asserted it and the arithmetic is consistent with itself". The typed outcomes
force the distinction at the point of construction. A score can be added
*within* an outcome; it cannot replace one.

**Rejected: `Determinate` / `Ambiguous` / `Unresolved`, i.e. keeping the old
three.** They are a taxonomy of the *solver's* epistemic state. They have no
vocabulary for the record being wrong, which is the single most valuable thing
a reconciliation engine can say, and no vocabulary for the difference between
"corroborated" and "arithmetically unique". Both distinctions are load-bearing
and neither is expressible.

**Rejected: making `Verified` require independent witness of composition.**
Correct in principle, empty in practice: no party outside the PSP ever sees a
batch form, so the outcome could never occur and every dataset would score
zero `Verified`. §3.3 states the weaker claim precisely instead, and
`rival_closure_count` measures how weak it is in each instance. Naming the
limit beats defining an unreachable ideal.

**Rejected: allowing `Reconstructed` on unique closure alone.** This is
remediation option 5 in `investigation/DEFECT_REPORT.md` §6, already measured:
67.00% on the primary set and 40.57% on held-out **with all 50 rows still
wrong**. Unique closure held at all three failing lines. Adopting it would
have shipped the known failure with a warrant attached.

**Rejected: gating on coverage instead of soundness.** A coverage gate alone
rewards guessing — which is how a 1.000 precision that
`investigation/DEFECT_REPORT.md` §2 calls *"a property of the dataset and the
tie-breaker"* got reported as an engine property. The contract gates
soundness broadly and coverage **narrowly**, on the subpopulation the corpus
can prove is determined. Both gates are needed; neither is sufficient.

**Rejected: `certain_rows` retained with a guard.** A guard on a property that
reads like an observation is a guard someone removes. The property stays;
the path from it to an assignment is deleted.

**Rejected: letting the resolver declare its own independence.** Tautological
(§7). The declaration is kept — a resolver must say what it thinks its
evidence rests on — but it is *validated*, not believed.

**Rejected: free-text `Unresolved` reasons.** They aggregate to nothing.
`no_subset_closes` and `enumeration_truncated` are different findings and the
second is the abstention loophole; an enum forces both to be counted.
