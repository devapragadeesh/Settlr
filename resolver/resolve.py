"""The resolver. Three tiers, one outcome per bank line, no answer without a
warrant.

    from resolver.resolve import resolve
    output = resolve(load(Path("corpus/datasets/A20_B100_Cmax")))

It is deliberately not clever. Every impulse toward sophistication here is an
impulse to add a code path that the corpus cannot exercise, and an unexercised
path is how defect D2 shipped: `stage3_solver.run` consumed pool rows on an
uncorroborated `Determinate` through an unguarded `elif` that never executed on
the only dataset in the repo, and on its first execution placed 50 rows into
the wrong bank line, starving the correct one. A 268-test suite said nothing
about it.

## The three tiers

**A -- ATTESTED.** The PSP's settlement report names this bank line (by the
bank's own reference), and the recon rows carry that settlement id. The
composition claim and the bank-line link both come from the PSP; the bank
supplies the amount the claim must predict.

**B -- PARTIALLY ATTESTED.** The recon rows carry a `settlement_id`, so a
composition claim exists, but no report row names this bank line. The link from
batch to line rests on the amount alone. This is the cell contract 6.3
predicted would be empty and was withdrawn for: the claim is present, it
entails a checkable prediction, and the prediction can hold.

**C -- UNATTESTED.** No composition claim reaches this line at all. Enumerate
every closing subset with no objective; `Reconstructed` only on unique closure
that is also exclusive across the window.

## What makes the old defects unrepresentable here

* Only `Verified` consumes. Contested rows stay in the pool (D2).
* There is no `certain_rows` path. Rows common to all candidates are reported
  as a property of the ambiguity and never assigned (D3).
* Uniqueness is tested against UNFILTERED closure. The ranking exists, is
  labelled a modelling assumption, and is applied strictly after enumeration
  (D1).
* Every `CandidateSet` exposes a rank-1 candidate, so contract 6.2's
  premise-sharing statistic is computable for the first time. The frozen
  cascade filters before enumerating, so it never exposes one.

## Settlement reversals: a two-pass resolution

`DECISIONS.md` 19 measured that a reversal makes a resolution wrong
RETROACTIVELY -- a date-ordered single pass cannot express it. Pass one scans
the bank file alone for debits that revoke an earlier credit; pass two resolves
credits in posting order, and a revoked credit is reported as an
`AttestationDiscrepancy(credit_reversed)` that assigns nothing and consumes
nothing. See `DECISIONS.md` 37 for the rejected alternative.

## Named limitations, stated here rather than discovered later

* **No residual reconstruction.** Tier B does not anchor on an attested core
  and reconstruct a residual over unattested rows, because attestation in this
  corpus is a property of a SETTLEMENT and never of a row: there is no dataset
  in which part of one batch is attested and part is not. Writing the path
  would produce exactly the unexercisable branch that D2 was.
* **A falsely attested line yields a finding, not an answer.** When the
  attestation is contradicted the contract's vocabulary offers
  `AttestationDiscrepancy`, which carries no composition, so a reachable
  `Reconstructed` is forgone. The vocabulary cannot say "the record is wrong
  AND here is what actually happened". See `DECISIONS.md` 34.
* **`CorrectlyUnmatched` reasons cite derived arithmetic over the PSP feed**,
  because the contract has no evidence kind meaning "a ledger field says so".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from resolver_contract.types import (
    Ambiguous, arithmetic_closure_over, AttestationDiscrepancy, CandidateSet,
    Composition, Contradiction, ContradictionKind, CorrectlyUnmatched,
    Evidence, EvidenceKind, LineOutcome, RankingAnnotation, Reconstructed,
    ResolverOutput, SourceSystem, UnmatchedReason, Unresolved,
    UnresolvedReason, Verified, Warrant,
)

from resolver.eligibility import IST, eligible_at, end_of_day, net, pool_at
from resolver.enumerate_closures import Closures, closing_subsets
from resolver.loaders import BankLine, Dataset

NAME = "evidence-tiered resolver v1"

#: How many days after a credit a debit may still be read as its reversal.
#: A window, not a rule: two lines of equal and opposite amount far apart are
#: two transactions, and calling them a reversal would invent a finding.
REVERSAL_WINDOW_DAYS = 7

#: The ranking. It is the generator's own selection rule (SETTLEMENT_SPEC 1.4),
#: applied STRICTLY AFTER a complete enumeration and labelled a modelling
#: assumption. That is the entire point of exposing it: if the resolver's
#: preference agrees with the generator's rule more often than 1/k, the two
#: share a premise, and contract 6.2 measures exactly that. Filtering on it
#: would be the D1 defect; ranking on it is the D1 MEASUREMENT.
RANKING = RankingAnnotation(
    objective="maximise applied debits, then maximise credit total",
    applied_after_enumeration=True,
    modelling_assumption=(
        "SETTLEMENT_SPEC.md 1.4 says a PSP applies as many pending debits as "
        "the balance allows. This is a MODELLING ASSUMPTION about the "
        "generator, it ranks an already-complete candidate set, and it never "
        "removes a candidate. If it agrees with the truth more often than "
        "1/k, this resolver shares a premise with whatever produced the data "
        "-- which is the finding, not the defence."))


# --------------------------------------------------------------------------
# evidence helpers -- provenance by construction, never by memory
# --------------------------------------------------------------------------

PSP = frozenset({SourceSystem.PSP_LEDGER})
#: The resolver's own enumeration. `SOURCE_PARTY` maps it to the party
#: `resolver`, which `NON_CORROBORATING_PARTIES` excludes from the independence
#: count -- a resolver's own arithmetic is not a witness to anything. Naming it
#: is how a reconstructed composition records that NOBODY claimed it.
SELF = frozenset({SourceSystem.RESOLVER_INTERNAL})
PSP_BOTH = frozenset({SourceSystem.PSP_LEDGER,
                      SourceSystem.PSP_SETTLEMENT_REPORT})
BANK = frozenset({SourceSystem.BANK})


def _bank_existence(line: BankLine) -> Evidence:
    """The bank says money of this amount arrived. It says NOTHING about which
    rows composed it (contract 3.2), and the type system knows that: both
    kinds here map to `Attests.EXISTENCE`."""
    if line.reference:
        return Evidence(
            kind=EvidenceKind.BANK_REFERENCE, derived_from=BANK,
            detail=f"bank reference {line.reference!r} for "
                   f"{line.amount_paise} paise on {line.value_date}")
    return Evidence(
        kind=EvidenceKind.BANK_VALUE_DATE, derived_from=BANK,
        detail=f"credit of {line.amount_paise} paise posted "
               f"{line.value_date}; the bank blanked its own reference")


def _composition_of(row_ids, rows_by_id) -> Composition:
    credits = sorted(r for r in row_ids if net(rows_by_id[r]) > 0)
    debits = sorted(r for r in row_ids if net(rows_by_id[r]) < 0)
    return Composition(
        credit_ids=tuple(credits), debit_ids=tuple(debits),
        credit_total=sum(net(rows_by_id[r]) for r in credits),
        debit_total=sum(-net(rows_by_id[r]) for r in debits))


def _rank(subsets, rows_by_id) -> list[tuple[str, ...]]:
    """Order a COMPLETE candidate set. Removes nothing."""
    def key(subset):
        debits = sum(1 for r in subset if net(rows_by_id[r]) < 0)
        credit = sum(net(rows_by_id[r]) for r in subset if net(rows_by_id[r]) > 0)
        return (-debits, -credit, subset)
    return sorted(subsets, key=key)


def _candidate_set(closures: Closures, rows_by_id) -> CandidateSet:
    ordered = _rank(closures.subsets, rows_by_id)
    return CandidateSet(
        candidates=tuple(_composition_of(s, rows_by_id) for s in ordered),
        complete=closures.complete, enumeration_cap=closures.cap,
        ranking=(RANKING,), ranked=True)


# --------------------------------------------------------------------------
# pass one: which credits does a later debit revoke?
# --------------------------------------------------------------------------


def revocations(bank: list[BankLine]) -> dict[int, int]:
    """`credit line index -> the debit line index that reverses it`.

    Computed from the BANK FILE ALONE, before any resolution, because a
    reversal invalidates a resolution retroactively and a date-ordered single
    pass cannot express that (`DECISIONS.md` 19: one reversal, two damaged bank
    lines, 50 misplaced rows).
    """
    found: dict[int, int] = {}
    claimed: set[int] = set()
    debits = [line for line in bank if not line.is_credit]
    for debit in sorted(debits, key=lambda l: (l.value_date, l.index)):
        window = timedelta(days=REVERSAL_WINDOW_DAYS)
        for credit in sorted(bank, key=lambda l: (l.value_date, l.index)):
            if (credit.is_credit and credit.index not in claimed
                    and credit.amount_paise == -debit.amount_paise
                    and credit.value_date <= debit.value_date
                    and debit.value_date - credit.value_date <= window):
                found[credit.index] = debit.index
                claimed.add(credit.index)
                break
    return found


# --------------------------------------------------------------------------
# the resolution
# --------------------------------------------------------------------------


@dataclass
class _State:
    rows_by_id: dict[str, dict]
    by_settlement: dict[str, list[str]]
    #: Rows spent by a `Verified`. ONLY `Verified` consumes (contract 2.4).
    consumed: set[str]
    unexplained_amounts: list[int]
    #: What each `Reconstructed` line built, kept so a collision between two
    #: reconstructions can be resolved symmetrically in pass three rather than
    #: by whichever line happened to be earlier.
    reconstructed: dict[int, dict] = field(default_factory=dict)


def resolve(dataset: Dataset, *, cap: int = 200,
            time_budget: float = 10.0) -> ResolverOutput:
    rows_by_id = {row["entity_id"]: row for row in dataset.rows}
    by_settlement: dict[str, list[str]] = defaultdict(list)
    for row in dataset.rows:
        settlement = row.get("settlement_id")
        if settlement:
            by_settlement[settlement].append(row["entity_id"])

    revoked = revocations(dataset.bank)
    credits = [line for line in dataset.bank if line.is_credit]
    state = _State(rows_by_id=rows_by_id, by_settlement=dict(by_settlement),
                   consumed=set(),
                   unexplained_amounts=[l.amount_paise for l in credits])

    # bank reference -> settlement, the PSP's own claim about the bank's
    # reference. It is a PSP field naming a BANK value; the direction is what
    # makes it a report rather than a fabrication (CORPUS_SPEC 5).
    by_reference = {entry["reported_reference"]: settlement
                    for settlement, entry in dataset.settlement_report.items()
                    if entry["reported_reference"]}

    outcomes: list[LineOutcome] = []
    for line in sorted(dataset.bank, key=lambda l: (l.value_date, l.index)):
        if not line.is_credit:
            outcomes.append(_debit_line(line, revoked))
            continue
        if line.index in revoked:
            outcomes.append(_reversed_credit(line, revoked[line.index],
                                             dataset, state))
            continue
        outcomes.append(_credit_line(line, dataset, state, by_reference,
                                     cap=cap, time_budget=time_budget))

    outcomes = _resolve_collisions(outcomes, state)
    assigned = {row_id for outcome in outcomes
                for row_id in outcome.assigned_rows}
    return ResolverOutput(
        resolver=NAME, dataset=dataset.name,
        line_outcomes=tuple(sorted(outcomes, key=lambda o: o.bank_index)),
        unmatched=tuple(unmatched_rows(dataset, assigned)))


def _resolve_collisions(outcomes: list[LineOutcome], state: _State
                        ) -> list[LineOutcome]:
    """Pass three: two lines cannot both own a row.

    `Reconstructed` ASSIGNS but does not CONSUME -- contract 2.4 gives
    consumption to `Verified` alone, so contested rows stay in the pool and a
    contested line cannot starve the next one (defect D2). The direct
    consequence, which only showed up when the resolver was first run across
    the whole corpus, is that two reconstructions can independently claim the
    same row, and `ResolverOutput.__post_init__` rejects that outright: a row
    settles once.

    That rejection is the type system doing its job, and the answer is not to
    weaken it. When claims collide:

    * a `Verified` wins -- two parties beat one party plus this resolver's
      arithmetic;
    * two `Reconstructed` both LOSE. Picking the earlier line would decide a
      genuine conflict by iteration order, which is the tie-breaker-as-evidence
      mistake that produced a 1.000 precision `investigation/DEFECT_REPORT.md`
      calls "a property of the dataset and the tie-breaker".

    Downgraded lines become `Unresolved`, keep the candidate they built so the
    oracle can still check the truth was inside it, and say what they collided
    with.
    """
    owners: dict[str, list[int]] = defaultdict(list)
    for outcome in outcomes:
        for row_id in outcome.assigned_rows:
            owners[row_id].append(outcome.bank_index)

    verified_lines = {o.bank_index for o in outcomes if isinstance(o, Verified)}
    doomed: dict[int, set[int]] = defaultdict(set)
    for row_id, claimants in owners.items():
        if len(claimants) < 2:
            continue
        winners = [index for index in claimants if index in verified_lines]
        losers = ([index for index in claimants if index not in verified_lines]
                  if len(winners) == 1 else list(claimants))
        for index in losers:
            doomed[index].update(set(claimants) - {index})
    if not doomed:
        return outcomes

    rebuilt: list[LineOutcome] = []
    for outcome in outcomes:
        if outcome.bank_index not in doomed:
            rebuilt.append(outcome)
            continue
        meta = state.reconstructed.get(outcome.bank_index, {})
        others = sorted(doomed[outcome.bank_index])
        rebuilt.append(Unresolved(
            bank_index=outcome.bank_index, reason=UnresolvedReason.OTHER,
            pool_size=meta.get("pool_size", 0),
            warrant=Warrant.over(
                [meta["existence"]] if meta.get("existence") else
                list(outcome.warrant.evidence),
                rationale="its only closing subset overlaps rows another line "
                          "also claims. A row settles once, and nothing in the "
                          "record says which line owns it."),
            detail="reconstruction collides with "
                   + ", ".join(f"bank[{index}]" for index in others)
                   + "; both claims are withdrawn rather than decided by "
                     "iteration order",
            partial_candidates=meta.get("candidate_set")))
    return rebuilt


def _debit_line(line: BankLine, revoked: dict[int, int]) -> Unresolved:
    """A debit is not a credit to explain. Reported, never silently dropped."""
    reverses = [credit for credit, debit in revoked.items()
                if debit == line.index]
    if reverses:
        return Unresolved(
            bank_index=line.index, reason=UnresolvedReason.OTHER, pool_size=0,
            warrant=Warrant.over(
                [Evidence(kind=EvidenceKind.BANK_VALUE_DATE, derived_from=BANK,
                          detail=f"debit of {-line.amount_paise} paise on "
                                 f"{line.value_date}, equal and opposite to "
                                 f"the credit at bank[{reverses[0]}]")],
                rationale="the bank's own record of a returned transfer"),
            detail=f"reversal debit revoking bank[{reverses[0]}]; the finding "
                   "is carried on the credit it revokes, not here")
    return Unresolved(
        bank_index=line.index, reason=UnresolvedReason.NOT_OUR_CREDIT,
        pool_size=0,
        warrant=Warrant.over(
            [Evidence(kind=EvidenceKind.BANK_VALUE_DATE, derived_from=BANK,
                      detail=f"debit of {-line.amount_paise} paise on "
                             f"{line.value_date}")],
            rationale="a debit on the merchant's account is not a settlement "
                      "credit; nothing about it is this resolver's to explain"),
        detail="bank debit, not a settlement credit")


def _reversed_credit(line: BankLine, debit_index: int, dataset: Dataset,
                     state: _State) -> AttestationDiscrepancy:
    """The bank took the money back. The PSP still says it settled.

    This is the retroactive case `DECISIONS.md` 19 measured, and it is the
    reason the resolution is two-pass. It assigns nothing and consumes nothing:
    a credit that was returned did not pay for any rows, and treating it as if
    it had is how one reversal damaged two bank lines.
    """
    contradiction = Contradiction(
        kind=ContradictionKind.CREDIT_REVERSED,
        detail=f"the credit of {line.amount_paise} paise posted "
               f"{line.value_date} was reversed by the debit at "
               f"bank[{debit_index}]. Any composition claimed for it is a "
               "claim about money that came back.",
        between=frozenset({SourceSystem.BANK, SourceSystem.PSP_LEDGER}))
    return AttestationDiscrepancy(
        bank_index=line.index, contradiction=contradiction,
        warrant=Warrant.over(
            [_bank_existence(line),
             Evidence(kind=EvidenceKind.BANK_VALUE_DATE, derived_from=BANK,
                      detail=f"reversing debit at bank[{debit_index}]")],
            rationale="the bank contradicts itself across two lines, and the "
                      "PSP's settlement record does not carry the reversal",
            contradictions=[contradiction]),
        bank_amount=line.amount_paise)


def _credit_line(line: BankLine, dataset: Dataset, state: _State,
                 by_reference: dict[str, str], *, cap: int,
                 time_budget: float) -> LineOutcome:
    settlement = by_reference.get(line.reference) if line.reference else None
    if settlement is not None:
        return _tier_a(line, settlement, dataset, state, cap, time_budget)
    if dataset.rows_carry_settlement_id:
        outcome = _tier_b(line, dataset, state, cap, time_budget)
        if outcome is not None:
            return outcome
    return _tier_c(line, dataset, state, cap, time_budget)


# --------------------------------------------------------------------------
# tier A -- the settlement report names this line
# --------------------------------------------------------------------------


def _tier_a(line: BankLine, settlement: str, dataset: Dataset, state: _State,
            cap: int, time_budget: float) -> LineOutcome:
    entry = dataset.settlement_report[settlement]
    claimed = sorted(state.by_settlement.get(settlement, ()))

    attestation = Evidence(
        kind=EvidenceKind.ATTESTED_SETTLEMENT_ID, derived_from=PSP_BOTH,
        detail=f"the PSP reports settlement {settlement} against bank "
               f"reference {line.reference!r} and names {len(claimed)} rows",
        supports=tuple(claimed))
    existence = _bank_existence(line)

    if not claimed:
        return _discrepancy(
            line, ContradictionKind.CLAIMED_CREDIT_NOT_ON_STATEMENT,
            f"the report names settlement {settlement} for this credit, but no "
            "recon row carries that settlement id",
            [attestation, existence], attested_net=None,
            bank_amount=line.amount_paise)

    # 1. the PSP's own two artefacts must agree with the bank about the AMOUNT
    if entry["reported_amount"] != line.amount_paise:
        return _discrepancy(
            line, ContradictionKind.CLAIMED_CREDIT_NOT_ON_STATEMENT,
            f"the PSP reports a payout of {entry['reported_amount']} paise for "
            f"{settlement}; the bank posted {line.amount_paise} paise under "
            f"the same reference. Difference "
            f"{entry['reported_amount'] - line.amount_paise} paise.",
            [attestation, existence],
            attested_net=entry["reported_amount"],
            bank_amount=line.amount_paise, rows=tuple(claimed))

    attested_net = sum(net(state.rows_by_id[r]) for r in claimed)

    # 2. does the claim's falsifiable consequence hold?
    if attested_net != line.amount_paise:
        return _discrepancy(
            line, ContradictionKind.ATTESTED_COMPOSITION_DOES_NOT_CLOSE,
            f"the {len(claimed)} rows attested to {settlement} net to "
            f"{attested_net} paise; the bank posted {line.amount_paise}. "
            f"Difference {attested_net - line.amount_paise} paise.",
            [attestation, existence], attested_net=attested_net,
            bank_amount=line.amount_paise, rows=tuple(claimed))

    # 3. could the named rows have been in this credit at all?
    #
    #    A row created after the money left cannot have been in the money that
    #    left. `created_at` is the PSP's field and `value_date` is the BANK's,
    #    so this is a contradiction between two parties -- which is what makes
    #    it worth anything. It is also the only check that sees a RESTATEMENT:
    #    a stale attestation whose rows were swapped for others of identical
    #    net closes arithmetically and is invisible to step 2.
    ceiling = end_of_day(line.value_date)
    impossible = sorted(r for r in claimed
                        if state.rows_by_id[r]["created_at"] > ceiling)
    if impossible:
        when = datetime.fromtimestamp(
            state.rows_by_id[impossible[0]]["created_at"], IST)
        return _discrepancy(
            line, ContradictionKind.TEMPORAL_IMPOSSIBILITY,
            f"{len(impossible)} of the {len(claimed)} rows attested to "
            f"{settlement} were created AFTER the bank posted this credit on "
            f"{line.value_date} (earliest offender {impossible[0]} at "
            f"{when:%Y-%m-%d %H:%M}). The arithmetic closes, so a sum check "
            "cannot see this; the rows are still impossible.",
            [attestation, existence], attested_net=attested_net,
            bank_amount=line.amount_paise, rows=tuple(impossible))

    # 4. a row settles once
    double = sorted(r for r in claimed if r in state.consumed)
    if double:
        return _discrepancy(
            line, ContradictionKind.DOUBLE_ASSIGNMENT,
            f"{len(double)} rows attested to {settlement} were already "
            f"consumed by an earlier settled credit: {double[:4]}",
            [attestation, existence], attested_net=attested_net,
            bank_amount=line.amount_paise, rows=tuple(double))

    return _verify(line, claimed, state, [attestation, existence],
                   rationale="the PSP named a composition; the BANK posted an "
                             "amount that composition predicts. Two parties, "
                             "one checkable consequence.",
                   cap=cap, time_budget=time_budget, dataset=dataset)


# --------------------------------------------------------------------------
# tier B -- a composition claim exists, but nothing links it to this line
# --------------------------------------------------------------------------


def _tier_b(line: BankLine, dataset: Dataset, state: _State, cap: int,
            time_budget: float) -> LineOutcome | None:
    """The recon rows claim a batch; the amount is the only link to this line.

    This is the cell contract 6.3 asserted was empty and was WITHDRAWN for.
    `settlement_id` is on the rows even at 0% report coverage, so a composition
    claim exists, it predicts an amount, and the prediction is checkable. The
    link is weaker than tier A's -- it rests on an amount rather than on a
    reference -- so when two unconsumed settlements net to the same amount this
    returns `Ambiguous` rather than picking one.
    """
    matches = []
    for settlement, row_ids in state.by_settlement.items():
        available = [r for r in row_ids if r not in state.consumed]
        if len(available) != len(row_ids):
            continue                       # partly spent: not this credit
        if sum(net(state.rows_by_id[r]) for r in available) == line.amount_paise:
            matches.append(sorted(available))
    if not matches:
        return None

    existence = _bank_existence(line)
    if len(matches) > 1:
        claim = Evidence(
            kind=EvidenceKind.ATTESTED_SETTLEMENT_ID, derived_from=PSP,
            detail=f"{len(matches)} distinct settlements claimed by the recon "
                   "rows net to this credit; the amount cannot say which")
        return Ambiguous(
            bank_index=line.index,
            candidate_set=CandidateSet(
                candidates=tuple(_composition_of(m, state.rows_by_id)
                                 for m in _rank(matches, state.rows_by_id)),
                complete=True, enumeration_cap=cap,
                ranking=(RANKING,), ranked=True),
            warrant=Warrant.over(
                [claim, existence],
                rationale="a composition claim exists for each candidate and "
                          "the bank confirms only that the amount arrived. "
                          "Naming one would assert a link no party made."))

    claimed = matches[0]
    settlement = next(s for s, ids in state.by_settlement.items()
                      if sorted(ids) == claimed)
    claim = Evidence(
        kind=EvidenceKind.ATTESTED_SETTLEMENT_ID, derived_from=PSP,
        detail=f"the recon rows claim {len(claimed)} rows form settlement "
               f"{settlement}; no settlement report names this bank line",
        supports=tuple(claimed))

    ceiling = end_of_day(line.value_date)
    impossible = sorted(r for r in claimed
                        if state.rows_by_id[r]["created_at"] > ceiling)
    if impossible:
        return _discrepancy(
            line, ContradictionKind.TEMPORAL_IMPOSSIBILITY,
            f"{len(impossible)} rows claimed for {settlement} were created "
            f"after the bank posted this credit on {line.value_date}",
            [claim, existence], attested_net=line.amount_paise,
            bank_amount=line.amount_paise, rows=tuple(impossible))

    return _verify(line, claimed, state, [claim, existence],
                   rationale="the PSP's ledger names a composition and the "
                             "BANK posted exactly what it predicts. The link "
                             "from batch to line is the amount alone, and no "
                             "other unconsumed settlement shares it.",
                   cap=cap, time_budget=time_budget, dataset=dataset)


# --------------------------------------------------------------------------
# tier C -- nothing claims this credit. Reconstruct, or decline.
# --------------------------------------------------------------------------


def _tier_c(line: BankLine, dataset: Dataset, state: _State, cap: int,
            time_budget: float) -> LineOutcome:
    pool = pool_at(dataset.rows, line.value_date, state.consumed)
    existence = _bank_existence(line)
    closures = closing_subsets(pool, line.amount_paise, cap=cap,
                               time_budget=time_budget)

    if closures.count == 0:
        return Unresolved(
            bank_index=line.index,
            reason=(UnresolvedReason.NO_SUBSET_CLOSES if closures.complete
                    else UnresolvedReason.ENUMERATION_TRUNCATED),
            pool_size=len(pool),
            warrant=Warrant.over([existence],
                                 rationale="the bank posted a credit no subset "
                                           "of the eligible pool explains"),
            detail=f"pool {len(pool)}; enumerator status {closures.status}")

    if not closures.complete:
        # One found under truncation is NOT uniqueness. Reporting it as
        # `Reconstructed` is how the hardest cells would produce the cleanest
        # numbers (contract 4.5).
        return Unresolved(
            bank_index=line.index,
            reason=UnresolvedReason.ENUMERATION_TRUNCATED,
            pool_size=len(pool),
            warrant=Warrant.over([existence],
                                 rationale="enumeration stopped before it could "
                                           "prove or disprove uniqueness"),
            detail=f"pool {len(pool)}; {closures.count} closing subsets found "
                   f"before {closures.status}; the true count is at least that",
            partial_candidates=_candidate_set(closures, state.rows_by_id))

    if closures.count > 1:
        return Ambiguous(
            bank_index=line.index,
            candidate_set=_candidate_set(closures, state.rows_by_id),
            warrant=Warrant.over(
                [existence,
                 Evidence(kind=EvidenceKind.ARITHMETIC_CLOSURE,
                          derived_from=PSP | BANK,
                          detail=f"{closures.count} subsets of a {len(pool)}-row "
                                 "pool close to this credit under no objective")],
                rationale="several compositions explain this credit equally "
                          "well and nothing in the record distinguishes them"))

    # exactly one, proven complete. Is it exclusive across the window?
    subset = closures.subsets[0]
    rivals = sum(1 for amount in state.unexplained_amounts
                 if amount == line.amount_paise) - 1
    if rivals > 0:
        # Unique closure is a PER-CREDIT predicate answering a CROSS-CREDIT
        # question. At all three bank lines that produced the 50 wrong rows the
        # pool admitted exactly one closing subset -- OPTIMAL, untruncated, no
        # tie to miss -- and the answer was still wrong, because those rows were
        # the true composition of a LATER credit (contract 4.3).
        #
        # `Ambiguous` is not available: there is one candidate, not two. So the
        # honest outcome is `Unresolved`, carrying the candidate it did build so
        # the oracle can still check whether the truth was inside it.
        return Unresolved(
            bank_index=line.index, reason=UnresolvedReason.OTHER,
            pool_size=len(pool),
            warrant=Warrant.over(
                [existence,
                 Evidence(kind=EvidenceKind.ARITHMETIC_CLOSURE,
                          derived_from=PSP | BANK,
                          detail="exactly one subset of the pool closes, and it "
                                 f"closes {rivals} other unexplained credit(s) "
                                 "in this window just as well")],
                rationale="cross-line exclusivity fails. Reconstructed requires "
                          "it precisely because per-credit uniqueness held at "
                          "every line that produced the 50 wrong rows."),
            detail=f"unique closure, but {rivals} other unexplained credit(s) "
                   "share this amount: the subset cannot be attributed to THIS "
                   "line",
            partial_candidates=_candidate_set(closures, state.rows_by_id))

    # The warrant deliberately does NOT carry the bank's existence evidence.
    #
    # `Reconstructed.__post_init__` refuses a warrant with two independent
    # parties, and it is right to: two parties agreeing is `Verified`, and
    # reporting that as `Reconstructed` would understate the claim. Here the
    # bank supplied the TARGET and said nothing whatever about composition
    # (contract 3.2), while the rows are the PSP's and the SELECTION is this
    # resolver's own. Listing the bank as a source of a composition claim would
    # manufacture an agreement that never happened -- circular corroboration,
    # in the exact shape defect D4 has. The amount and date are named in the
    # detail instead, where they are a target rather than a witness.
    unique = Evidence(
        kind=EvidenceKind.UNIQUE_CLOSURE_UNFILTERED, derived_from=PSP | SELF,
        detail=f"exactly one subset of the {len(pool)}-row eligible pool closes "
               f"to the {line.amount_paise} paise the bank posted on "
               f"{line.value_date}, established with NO objective filtering the "
               "candidate set. The rows are the PSP's; the selection is this "
               "resolver's; the bank named only the target.",
        supports=tuple(subset))
    exclusive = Evidence(
        kind=EvidenceKind.CROSS_LINE_EXCLUSIVITY, derived_from=PSP | SELF,
        detail="that subset closes no other unexplained credit in the window "
               f"{min(l.value_date for l in dataset.bank)} .. "
               f"{max(l.value_date for l in dataset.bank)}",
        supports=tuple(subset))
    state.reconstructed[line.index] = {
        "pool_size": len(pool), "existence": existence,
        "candidate_set": _candidate_set(closures, state.rows_by_id)}
    return Reconstructed(
        bank_index=line.index,
        composition=_composition_of(subset, state.rows_by_id),
        warrant=Warrant.over(
            [unique, exclusive],
            rationale="NO party claims this credit. One composition explains "
                      "it, no objective was used to reach that, and no other "
                      "unexplained credit in the window shares its amount. "
                      "One party's rows and this resolver's arithmetic -- "
                      "STRICTLY WEAKER than Verified, and it does not consume."))


# --------------------------------------------------------------------------
# outcome constructors
# --------------------------------------------------------------------------


def _verify(line: BankLine, claimed: list[str], state: _State,
            evidence: list[Evidence], *, rationale: str, cap: int,
            time_budget: float, dataset: Dataset) -> Verified:
    """Build the `Verified`, including the MANDATORY rival closure count.

    Contract 3.3: a consequence confirmed when 400 rival compositions predict
    the same consequence is weak corroboration of THIS one. The count is
    measured rather than assumed, `0` is rejected at construction because 0
    means unmeasured, and a truncated count is flagged as the lower bound it
    is.
    """
    pool = pool_at(dataset.rows, line.value_date, state.consumed)
    closures = closing_subsets(pool, line.amount_paise, cap=cap,
                               time_budget=time_budget)
    rivals = max(closures.count, 1)      # the claimed composition is one of them

    closes = arithmetic_closure_over(
        [SourceSystem.PSP_LEDGER, SourceSystem.BANK],
        detail=f"the {len(claimed)} attested rows net to {line.amount_paise} "
               "paise, which is what the bank actually paid",
        supports=tuple(claimed),
        kind=EvidenceKind.ATTESTED_COMPOSITION_CLOSES)

    outcome = Verified(
        bank_index=line.index,
        composition=_composition_of(claimed, state.rows_by_id),
        warrant=Warrant.over(evidence + [closes], rationale=rationale),
        rival_closure_count=rivals,
        rival_count_is_lower_bound=not closures.complete)
    # ONLY Verified consumes. Contested rows stay in the pool (contract 2.4).
    state.consumed.update(claimed)
    if line.amount_paise in state.unexplained_amounts:
        state.unexplained_amounts.remove(line.amount_paise)
    return outcome


def _discrepancy(line: BankLine, kind: ContradictionKind, detail: str,
                 evidence: list[Evidence], *, attested_net: int | None,
                 bank_amount: int | None,
                 rows: tuple[str, ...] = ()) -> AttestationDiscrepancy:
    """The sources disagree. Carries NO composition, by contract 4.2: a
    discrepancy is a finding about the record, not a claim about which rows
    settled. It consumes nothing, so a contradicted line cannot starve the
    next one."""
    contradiction = Contradiction(
        kind=kind, detail=detail,
        between=frozenset({SourceSystem.PSP_LEDGER, SourceSystem.BANK}),
        row_ids=rows)
    return AttestationDiscrepancy(
        bank_index=line.index, contradiction=contradiction,
        warrant=Warrant.over(
            evidence,
            rationale="two parties disagree about this credit, and the "
                      "disagreement is the finding",
            contradictions=[contradiction]),
        attested_row_ids=rows, attested_net=attested_net,
        bank_amount=bank_amount)


# --------------------------------------------------------------------------
# rows that correctly have no bank credit
# --------------------------------------------------------------------------


def unmatched_rows(dataset: Dataset, consumed: set[str]
                   ) -> list[CorrectlyUnmatched]:
    """A DERIVED reason per unassigned row. The oracle scores the reason.

    The contract has no evidence kind meaning "a ledger field says so", so each
    reason declares derived arithmetic over the PSP feed and says which fields
    it read. That is a limitation of the vocabulary, named here rather than
    papered over with a kind that means something else.
    """
    rows_by_id = {row["entity_id"]: row for row in dataset.rows}
    horizon = max(line.value_date for line in dataset.bank)
    refunded: dict[str, int] = defaultdict(int)
    for row in dataset.rows:
        if row["type"] == "refund" and row.get("payment_id"):
            refunded[row["payment_id"]] += row["debit"]

    buckets: dict[UnmatchedReason, list[str]] = defaultdict(list)
    for row in dataset.rows:
        row_id = row["entity_id"]
        if row_id in consumed:
            continue
        buckets[_unmatched_reason(row, rows_by_id, refunded, horizon)].append(row_id)

    out: list[CorrectlyUnmatched] = []
    for reason, row_ids in sorted(buckets.items(), key=lambda kv: kv[0].value):
        out.append(CorrectlyUnmatched(
            row_ids=tuple(sorted(row_ids)), reason=reason,
            warrant=Warrant.over(
                [Evidence(kind=EvidenceKind.ARITHMETIC_CLOSURE,
                          derived_from=PSP,
                          detail=f"{reason.value}: derived from the recon "
                                 "feed's own created_at / on_hold / credit / "
                                 "refund columns, over rows no bank credit "
                                 "explains")],
                rationale="a reason derived from the ledger, not a label "
                          "applied to whatever was left over")))
    return out


def _unmatched_reason(row, rows_by_id, refunded, horizon) -> UnmatchedReason:
    if row["type"] == "payment" and row["credit"] == 0:
        return UnmatchedReason.FAILED_AT_GATEWAY
    if row.get("on_hold"):
        return UnmatchedReason.DISPUTE_HELD
    if row["type"] == "payment":
        if refunded.get(row["entity_id"], 0) >= row["credit"] > 0:
            return UnmatchedReason.NETTED_OUT
        if eligible_at(row["created_at"]) > end_of_day(horizon):
            return UnmatchedReason.NOT_YET_ELIGIBLE
        return UnmatchedReason.ROLLED_FORWARD
    if row["type"] == "refund":
        parent = rows_by_id.get(row.get("payment_id") or "")
        if parent and refunded.get(parent["entity_id"], 0) >= parent["credit"] > 0:
            return UnmatchedReason.NETTED_OUT
    return UnmatchedReason.DEBIT_DEFERRED
