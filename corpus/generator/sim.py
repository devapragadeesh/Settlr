"""The corpus batch-formation loop.

## Why this file exists at all

`engine/simulator.py` is frozen and two things the corpus needs are *inside*
frozen function bodies:

* `utr = f"{t}{settlement_id[-6:]}"` -- defect D4. The bank's reference is a
  pure function of ledger state, so `bank_statement.csv` re-encodes the
  attestation and "12/12 matched on UTR" measures the generator, not a solver.
  It is a statement in a function body, not a rebindable module constant, so
  the monkeypatch pattern `holdout/generate_holdout.py` uses cannot reach it.
* `SELECTION_RULES` has exactly two entries. Axis C needs a third with no
  objective at all.

## What is re-implemented and what is imported

**Only the loop.** Every arithmetic primitive is IMPORTED from the frozen
module -- importing is not touching, and a second copy of the fee model is a
second place for it to drift:

    compute_fee, ceil_div, MDR, CARD_MDR   fee is identical to the paise
    add_working_days                       T+2 eligibility
    max_subsets_under_cap, fifo_under_cap  readings (B) and (E)
    PaymentEvent, RefundEvent, AdjustmentEvent, Batch, SimulationResult

Preserved deliberately, because they are the subtle parts of
`SETTLEMENT_SPEC.md` §1.2 and a re-implementation would plausibly get them
wrong: `available(t)` counts credits from payments that are **not yet
eligible**; the net-out rule; hold semantics; §1.4 largest-first debit
deferral and the batch skip; the lexicographically-smallest winner.

## The drift risk, and the test that closes it

Two implementations of one spec silently disagree, and then every corpus
number measures a different rule than the frozen numbers -- so the panel's
first question, *"are these comparable?"*, has no answer.

`corpus/tests/test_conformance.py` closes it by **differential test**: at the
frozen configuration point (`max_under_cap`, `max_pool=28`, the frozen batch
times) this loop must reproduce `engine.simulator.simulate` exactly, on the
frozen ledger and on seeded random ledgers. That makes the frozen
configuration a corpus axis point, and every other axis point a controlled
deviation from a verified baseline rather than an unanchored new artefact.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Callable, Sequence

from engine.simulator import (          # imported, never re-typed
    IST, AdjustmentEvent, Batch, PaymentEvent, RefundEvent, SimulationResult,
    add_working_days, ceil_div, compute_fee, fifo_under_cap,
    max_subsets_under_cap,
)

__all__ = ["CorpusConfig", "simulate", "random_valid", "SELECTION_RULES"]


# --------------------------------------------------------------------------
# random_valid -- reading (F), the premise-free selection rule
# --------------------------------------------------------------------------


def _achievable_sums(items: Sequence[tuple[str, int]], cap: int
                     ) -> list[dict[int, int]]:
    """Counting DP: `layer[i][s]` = number of subsets of `items[i:]` summing to s.

    Bounded by `cap`, so it is O(n · cap) in table entries, not 2^n. The shape
    already exists in `engine/generator._largest_ambiguous_sum`; here it counts
    rather than merely marking reachability, because the count is what makes
    uniform sampling possible.
    """
    layers: list[dict[int, int]] = [{0: 1}]
    for _name, value in reversed(items):
        previous = layers[-1]
        current = dict(previous)
        for total, count in previous.items():
            if total + value <= cap:
                current[total + value] = current.get(total + value, 0) + count
        layers.append(current)
    layers.reverse()
    return layers


def random_valid(
    items: Sequence[tuple[str, int]], cap: int, tie_limit: int = 64, *,
    rng: random.Random | None = None,
    floor_fraction: Fraction = Fraction(9, 10),
) -> tuple[int, list[tuple[str, ...]], bool]:
    """Uniform sample from the feasible subsets in a band below the cap.

    ## Why a band and not "any feasible subset"

    `Σcredit(S) ≤ available(t)` alone admits `S = ∅`. Under it money would
    rarely settle, pools would grow without bound, and pool size would become
    an OUTCOME rather than a controlled variable -- confounding axis A with
    axis C. Uniform-over-all-subsets is no better: by mass it concentrates near
    half the rows, draining about half the pool per batch.

    So:

        S ~ Uniform{ S ⊆ E(t) : φ·cap ≤ Σcredit(S) ≤ cap },   φ = 9/10

    which has **no objective a solver could share** -- it is not an argmax of
    anything, and nothing prefers more debits, older rows, larger cardinality,
    or a larger sum beyond the band -- while draining at a rate comparable to
    `max_under_cap` so axis A stays controlled.

    ## Why this rule exists

    `investigation/DEFECT_REPORT.md` §2: the frozen solver's "maximise applied
    debits" tie-break agrees with the generator because **both descend from
    `SETTLEMENT_SPEC.md` §1.4**. Solver and generator share a premise, and the
    shared premise was decisive on 4 of 4 primary credits where it mattered.
    A rule with no objective is the control condition for that.

    ## The sampler is genuinely uniform, and where it stops being so

    Sample the target sum with probability proportional to the NUMBER of
    subsets achieving it, then trace back uniformly among those subsets. That
    is exactly uniform over the band. The DP table is O(n · cap) integers, so
    it is fine to pool ~60 at these amounts.

    Returns `(chosen_sum, [one_subset], False)` -- the same shape as
    `max_subsets_under_cap`, so the loop's `select(...)` call is unchanged.
    There is no tie register under this rule: see `CorpusConfig` and
    `corpus/CORPUS_SPEC.md` §4 for why that is a statement about the rule
    rather than a missing feature.

    ## Flagged modelling assumption

    At φ=0.9 the rule still weakly shares "bigger is likelier" with any solver
    preferring large closing subsets. φ is the knob trading economic realism
    against premise independence, it is recorded per dataset, and one axis
    point runs at φ=0 as the premise-free extreme.
    """
    rng = rng or random.Random(0)
    if not items or cap <= 0:
        return 0, [()], False

    ordered = sorted(items, key=lambda kv: kv[0])
    layers = _achievable_sums(ordered, cap)
    floor = int(Fraction(cap) * floor_fraction)

    band = {total: count for total, count in layers[0].items()
            if floor <= total <= cap and count > 0}
    if not band:
        # No subset lands in the band. Falling back is recorded on the batch
        # as `selection_fallback`, never silently swallowed.
        best, winners, truncated = max_subsets_under_cap(ordered, cap, tie_limit)
        return best, winners, truncated

    totals = sorted(band)
    weights = [band[t] for t in totals]
    target = rng.choices(totals, weights=weights, k=1)[0]

    chosen: list[str] = []
    remaining = target
    for index, (name, value) in enumerate(ordered):
        # P(include) = (subsets of the tail achieving remaining-value)
        #            / (subsets of the tail achieving remaining)
        tail = layers[index + 1]
        with_it = tail.get(remaining - value, 0) if value <= remaining else 0
        total_here = layers[index].get(remaining, 0)
        if total_here == 0:
            break
        if rng.randrange(total_here) < with_it:
            chosen.append(name)
            remaining -= value
    return target - remaining if remaining else target, [tuple(sorted(chosen))], False


SELECTION_RULES: dict[str, Callable] = {
    "max_under_cap": max_subsets_under_cap,
    "fifo_under_cap": fifo_under_cap,
    "random_valid": random_valid,
}


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusConfig:
    """Everything the corpus varies. Note what is NOT here: any bank-side
    field. The batch does not know its bank reference, because under D4's fix
    the bank mints it and the batch is never told (`corpus/generator/bank.py`).
    """

    batch_times: Sequence[int]
    settlement_delay_working_days: int = 2
    cutoff_hour: int = 17
    #: Pool ceiling. Above it the frozen simulator degrades to FIFO and says
    #: so (SETTLEMENT_SPEC §1.5). Axis A deliberately runs above 28, so
    #: datasets targeting pools of 40 and 60 raise this AND use a selection
    #: rule that is tractable there -- which `max_under_cap` is not.
    max_pool: int = 28
    selection_rule: str = "max_under_cap"
    #: `random_valid` only. See its docstring.
    floor_fraction: Fraction = Fraction(9, 10)
    #: Tie enumeration limit for `max_under_cap`. The register above it is a
    #: SAMPLE, and the batch says so.
    tie_limit: int = 64
    rng_seed: int = 0


@dataclass
class CorpusBatch(Batch):
    """A frozen `Batch` plus what the corpus needs to be honest about.

    `Batch` has no field for "the selection rule could not be applied and
    something else was", and adding one to a frozen dataclass is not an
    option, so it is added here.
    """

    selection_fallback: str | None = None
    sampler: str = "exact"


def simulate(
    payments: Sequence[PaymentEvent],
    refunds: Sequence[RefundEvent],
    adjustments: Sequence[AdjustmentEvent],
    config: CorpusConfig,
    id_maker=None,
) -> SimulationResult:
    """Run SETTLEMENT_SPEC.md §1.2 over a ledger.

    Line-for-line the frozen `engine.simulator.simulate`, with exactly three
    deviations, each of which is the reason this file exists:

    1. **no UTR.** `Batch.utr` is set to `""`. The bank mints its own reference
       and is never shown a settlement id (defect D4).
    2. **`random_valid` is available**, and needs the rng threaded to it.
    3. **`selection_fallback` is recorded** when the band was unreachable.

    Everything else -- `available(t)` including not-yet-eligible credits, the
    net-out rule, holds, §1.4 deferral, the batch skip, the
    lexicographically-smallest winner -- is preserved deliberately and is
    asserted equal to the frozen implementation by
    `corpus/tests/test_conformance.py`.
    """
    rng = random.Random(config.rng_seed)
    payments = sorted(payments, key=lambda p: (p.created_at, p.id))
    refunds = sorted(refunds, key=lambda r: (r.created_at, r.id))
    adjustments = sorted(adjustments, key=lambda a: (a.created_at, a.id))

    by_id = {p.id: p for p in payments}
    eligible_at = {
        p.id: add_working_days(p.created_at,
                               config.settlement_delay_working_days,
                               config.cutoff_hour)
        for p in payments
    }

    refunds_for: dict[str, list[RefundEvent]] = {}
    for refund in refunds:
        refunds_for.setdefault(refund.payment_id, []).append(refund)

    netted_out: set[str] = set()
    netted_refunds: set[str] = set()
    for payment in payments:
        against = refunds_for.get(payment.id, [])
        if not against:
            continue
        if (sum(r.amount for r in against) == payment.amount
                and all(r.created_at <= eligible_at[payment.id] for r in against)):
            netted_out.add(payment.id)
            netted_refunds.update(r.id for r in against)

    settled_in: dict[str, str] = {}
    batches: list[CorpusBatch] = []

    def on_hold(payment: PaymentEvent, when: int) -> bool:
        if payment.hold_from is None or when < payment.hold_from:
            return False
        return payment.hold_until is None or when < payment.hold_until

    debit_events: list[tuple[str, int, int]] = [
        (r.id, r.amount, r.created_at) for r in refunds
        if r.id not in netted_refunds
    ] + [
        (a.id, a.amount if a.direction == "debit" else -a.amount, a.created_at)
        for a in adjustments
    ]

    for index, when in enumerate(sorted(config.batch_times)):
        available = sum(
            p.credit for p in payments
            if p.captured and p.created_at <= when and p.id not in settled_in
            and p.id not in netted_out and not on_hold(p, when))
        pending = sorted(
            (d for d in debit_events if d[2] <= when and d[0] not in settled_in),
            key=lambda d: (d[2], d[0]))
        available -= sum(d[1] for d in pending)

        pool = [
            (p.id, p.credit) for p in payments
            if p.captured and p.id not in settled_in and p.id not in netted_out
            and not on_hold(p, when) and eligible_at[p.id] <= when
        ]
        pool.sort(key=lambda kv: (by_id[kv[0]].created_at, kv[0]))

        degraded = len(pool) > config.max_pool
        fallback = None
        if degraded:
            select, sampler = fifo_under_cap, "fifo_degraded"
        elif config.selection_rule == "random_valid":
            def select(items, cap, tie_limit=config.tie_limit):
                return random_valid(items, cap, tie_limit, rng=rng,
                                    floor_fraction=config.floor_fraction)
            sampler = "uniform_band_dp"
        else:
            select = SELECTION_RULES[config.selection_rule]
            sampler = "exact"

        best, winners, truncated = select(pool, max(available, 0),
                                          config.tie_limit)
        chosen = winners[0] if winners else ()
        if config.selection_rule == "random_valid" and not degraded:
            floor = int(Fraction(max(available, 0)) * config.floor_fraction)
            if best < floor:
                fallback = "floor_unreachable"
                sampler = "max_under_cap_fallback"

        debits = list(pending)

        def split(items):
            positive = sum(d[1] for d in items if d[1] > 0)
            negative = sum(-d[1] for d in items if d[1] < 0)
            return best + negative, positive

        credit_total, debit_total = split(debits)
        while debits and credit_total - debit_total < 0:
            debits.sort(key=lambda d: (-d[1], d[0]))
            debits.pop(0)
            credit_total, debit_total = split(debits)
        if credit_total - debit_total < 0:
            continue
        if not chosen and not debits:
            continue

        settlement_id = id_maker("setl") if id_maker else f"setl_{index:014d}"
        for entity_id in chosen:
            settled_in[entity_id] = settlement_id
        for debit in debits:
            settled_in[debit[0]] = settlement_id

        batches.append(CorpusBatch(
            settlement_id=settlement_id,
            utr="",                       # D4: the batch has no bank reference
            formed_at=when, available=available,
            credit_ids=tuple(sorted(chosen)),
            debit_ids=tuple(sorted(d[0] for d in debits)),
            selected_credit=best, credit_total=credit_total,
            debit_total=debit_total, payout=credit_total - debit_total,
            ambiguous=len(winners) > 1 or truncated,
            tying_decompositions=[tuple(w) for w in winners],
            tying_decompositions_truncated=truncated,
            selection_degraded=degraded, pool_size=len(pool),
            selection_fallback=fallback, sampler=sampler))

    unsettled_reason: dict[str, str] = {}
    horizon = max(config.batch_times)
    for payment in payments:
        if payment.id in settled_in:
            continue
        if not payment.captured:
            unsettled_reason[payment.id] = "not_captured"
        elif payment.id in netted_out:
            unsettled_reason[payment.id] = "netted_out_by_full_refund"
        elif on_hold(payment, horizon):
            unsettled_reason[payment.id] = "on_hold_dispute"
        elif eligible_at[payment.id] > horizon:
            unsettled_reason[payment.id] = "not_yet_eligible_at_horizon"
        else:
            unsettled_reason[payment.id] = "rolled_forward_past_horizon"
    for refund in refunds:
        if refund.id in settled_in:
            continue
        unsettled_reason[refund.id] = (
            "netted_out_by_full_refund" if refund.id in netted_refunds
            else "debit_deferred_past_horizon")
    for adjustment in adjustments:
        if adjustment.id not in settled_in:
            unsettled_reason[adjustment.id] = "debit_deferred_past_horizon"

    return SimulationResult(batches=batches, settled_in=settled_in,
                            unsettled_reason=unsettled_reason,
                            netted_out=netted_out)
