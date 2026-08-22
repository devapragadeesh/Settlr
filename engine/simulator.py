"""Deterministic Razorpay settlement-batching simulator.

Implements SETTLEMENT_SPEC.md and nothing else. This module contains NO
matching, solving or reconciliation logic -- it produces data, and the true
decomposition of that data, for a solver it never imports.

All monetary quantities are ints in paise. There is no float arithmetic in
this file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

IST = timezone(timedelta(hours=5, minutes=30))

# --- fee model (SETTLEMENT_SPEC.md sec 4.1, reverse-engineered from 14/14
# --- captured rows, exact to the paise) ------------------------------------

GST_RATE_NUM, GST_RATE_DEN = 18, 100

#: MDR as an exact rational (numerator, denominator) over `amount`.
#:
#: Only the netbanking and wallet entries are `captured_real`: 2.000000% on
#: every one of the 14 fee-bearing captured rows. Everything else is
#: Razorpay's PUBLISHED pricing, not observed -- the captured account produced
#: zero card and zero UPI payments.
#:
#:  - 2% domestic netbanking / wallets / Visa / Mastercard / RuPay credit
#:  - 3% Amex, Diners and international cards
#:  - 2% UPI. Zero-MDR under Sec 269SU IT Act binds banks and system
#:    providers, NOT the aggregator's platform fee, and Razorpay bills it.
#:    Claiming UPI is free would contradict Razorpay's own price list.
#:  - RuPay DEBIT at zero. This one is statutory (Sec 269SU / Sec 10A PSS
#:    Act) rather than taken from Razorpay's table, which does not itemise
#:    it; tier `synthesized_modelled`. See SETTLEMENT_SPEC.md sec 4.3.
MDR = {
    "netbanking": (2, 100),
    "wallet": (2, 100),
    "upi": (2, 100),
    "card": (2, 100),
}
#: (network, card_type) overrides, applied before the `card` default.
CARD_MDR = {
    ("Amex", "credit"): (3, 100),
    ("Amex", "debit"): (3, 100),
    ("Diners", "credit"): (3, 100),
    ("RuPay", "debit"): (0, 100),
}


def ceil_div(num: int, den: int) -> int:
    """Exact integer ceiling division. No floats."""
    return -(-num // den)


def compute_fee(
    amount_paise: int,
    method: str,
    card_network: str | None = None,
    card_type: str | None = None,
    gst_applies: bool = True,
) -> tuple[int, int]:
    """Return ``(fee_incl_tax, tax)`` in paise.

    ``fee`` is INCLUSIVE of ``tax`` -- ``credit = amount - fee``. See
    SETTLEMENT_SPEC.md sec 4.

    ``gst_applies=False`` reproduces the ``tax: 0`` shape of Razorpay's own
    published recon sample row, on which the two candidate identities are
    indistinguishable.
    """
    num, den = CARD_MDR.get((card_network, card_type), MDR[method])
    fee_excl = ceil_div(amount_paise * num, den)
    tax = ceil_div(fee_excl * GST_RATE_NUM, GST_RATE_DEN) if gst_applies else 0
    return fee_excl + tax, tax


# --- ledger events ---------------------------------------------------------


@dataclass(frozen=True)
class PaymentEvent:
    id: str
    order_id: str | None
    order_receipt: str | None
    amount: int
    fee: int | None
    tax: int | None
    method: str
    created_at: int
    captured: bool
    notes: dict | list
    description: str | None = None
    bank: str | None = None
    wallet: str | None = None
    card_network: str | None = None
    card_issuer: str | None = None
    card_type: str | None = None
    dispute_id: str | None = None
    #: unix ts from which the payment is on hold (dispute opened)
    hold_from: int | None = None
    #: unix ts at which the hold releases (dispute won). None => never releases
    #: within the simulated window (still open, or lost).
    hold_until: int | None = None
    source_tier: str = "synthesized_modelled"
    source_ref: str = ""

    @property
    def credit(self) -> int:
        return self.amount - (self.fee or 0)


@dataclass(frozen=True)
class RefundEvent:
    id: str
    payment_id: str
    amount: int
    created_at: int
    notes: dict | list
    description: str | None = None
    source_tier: str = "synthesized_modelled"
    source_ref: str = ""


@dataclass(frozen=True)
class AdjustmentEvent:
    id: str
    amount: int
    created_at: int
    description: str
    #: "debit" (money out of the merchant, e.g. a lost dispute) or "credit"
    direction: str = "debit"
    dispute_id: str | None = None
    source_tier: str = "synthesized_modelled"
    source_ref: str = ""


@dataclass(frozen=True)
class SimulatorConfig:
    #: batch formation times, unix ts, ascending
    batch_times: Sequence[int]
    settlement_delay_working_days: int = 2
    #: cut-off clock for the T+N boundary, IST
    cutoff_hour: int = 17
    #: hard ceiling on the eligible pool per batch; keeps exact
    #: meet-in-the-middle enumeration tractable and bounded. Meet-in-the-middle
    #: materialises 2**(n/2) subsets per half, so 28 is ~16k per half -- fast --
    #: while 40 is ~1M per half and effectively hangs. A real merchant settles
    #: hundreds to thousands per batch, where exact enumeration is the wrong
    #: algorithm entirely; above this ceiling the batch degrades to the FIFO
    #: reading and says so. See SETTLEMENT_SPEC.md sec 1.5.
    max_pool: int = 28
    #: which reading of the documented rule to apply. See sec 1.1.
    selection_rule: str = "max_under_cap"


# --- eligibility -----------------------------------------------------------


def add_working_days(ts: int, days: int, cutoff_hour: int) -> int:
    """T+N working days at ``cutoff_hour`` IST, skipping Sat/Sun."""
    dt = datetime.fromtimestamp(ts, IST)
    remaining = days
    while remaining > 0:
        dt = dt + timedelta(days=1)
        if dt.weekday() < 5:
            remaining -= 1
    dt = dt.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
    return int(dt.timestamp())


# --- exact maximal subset-sum, with full tie enumeration -------------------


def max_subsets_under_cap(
    items: Sequence[tuple[str, int]], cap: int, tie_limit: int = 64
) -> tuple[int, list[tuple[str, ...]], bool]:
    """Meet-in-the-middle exact subset-sum.

    ``items`` is a sequence of ``(id, value)``. Returns
    ``(best_sum, subsets, truncated)`` where ``best_sum`` is the largest
    achievable ``<= cap`` and ``subsets`` is EVERY distinct subset achieving
    it.

    If more than ``tie_limit`` subsets tie, enumeration stops and ``truncated``
    is True. Such a batch is MORE ambiguous, not less, and the ground truth
    records it as "more than N, not enumerated". Silently returning a partial
    list as if it were complete would be a ground-truth lie; so would raising
    and pretending the case does not exist.

    Determinism: subsets are returned sorted; ids within a subset are sorted.
    """
    if cap < 0:
        return 0, [()], False
    ordered = sorted(items, key=lambda kv: (kv[1], kv[0]))
    half = len(ordered) // 2
    left, right = ordered[:half], ordered[half:]

    # Never keep more than `tie_limit + 1` subsets for any one partial sum:
    # the caller can only ever report `tie_limit` ties before it flips to
    # `truncated`, so the surplus is pure cost. Without this cap a degenerate
    # pool materialises 2**(n/2) tuples per half and the solver effectively
    # hangs. With it, a case with <= tie_limit ties is still enumerated
    # exactly; beyond that the result is truncated, and says so.
    keep = tie_limit + 1

    def enumerate_half(part: Sequence[tuple[str, int]]) -> dict[int, list[tuple[str, ...]]]:
        acc: dict[int, list[tuple[str, ...]]] = {0: [()]}
        for name, value in part:
            nxt: dict[int, list[tuple[str, ...]]] = {}
            for total, subsets in acc.items():
                bucket = nxt.setdefault(total, [])
                bucket.extend(subsets[: keep - len(bucket)])
                if total + value <= cap:
                    grown = nxt.setdefault(total + value, [])
                    grown.extend(
                        tuple(sorted(s + (name,)))
                        for s in subsets[: keep - len(grown)]
                    )
            acc = nxt
        return acc

    lmap = enumerate_half(left)
    rmap = enumerate_half(right)
    right_totals = sorted(rmap)

    best = -1
    for ltotal in sorted(lmap):
        if ltotal > cap:
            continue
        room = cap - ltotal
        # largest right total <= room
        lo, hi = 0, len(right_totals) - 1
        found = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if right_totals[mid] <= room:
                found = right_totals[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        if found is not None and ltotal + found > best:
            best = ltotal + found
    if best < 0:
        return 0, [()], False

    winners: set[tuple[str, ...]] = set()
    truncated = False
    for ltotal, lsubs in sorted(lmap.items()):
        rtotal = best - ltotal
        if rtotal < 0 or rtotal not in rmap:
            continue
        for ls in lsubs:
            for rs in rmap[rtotal]:
                winners.add(tuple(sorted(ls + rs)))
                if len(winners) > tie_limit:
                    truncated = True
                    break
            if truncated:
                break
        if truncated:
            break
    return best, sorted(winners), truncated


def fifo_under_cap(
    items: Sequence[tuple[str, int]], cap: int, tie_limit: int = 64
) -> tuple[int, list[tuple[str, ...]], bool]:
    """Oldest-first greedy fill under the same cap.

    The alternative reading of the documented rule (SETTLEMENT_SPEC.md sec 1.1
    reading E): take eligible payments in capture order until the next one
    would breach live balance. Never ambiguous, and O(n) rather than
    exponential -- which is what a production settlement service at merchant
    scale would plausibly do. Kept here so the reading is a swappable
    parameter rather than a buried assumption.

    `items` must already be in the caller's intended order.
    """
    total = 0
    chosen: list[str] = []
    for name, value in items:
        if total + value <= cap:
            total += value
            chosen.append(name)
    return total, [tuple(sorted(chosen))], False


SELECTION_RULES = {
    "max_under_cap": max_subsets_under_cap,
    "fifo_under_cap": fifo_under_cap,
}

# --- simulation ------------------------------------------------------------


@dataclass
class Batch:
    settlement_id: str
    utr: str
    formed_at: int
    available: int
    credit_ids: tuple[str, ...]
    debit_ids: tuple[str, ...]
    #: the quantity the documented rule actually constrains: the sum of the
    #: SELECTED PAYMENTS' credits, which must be <= `available`.
    selected_credit: int
    #: the `credit` COLUMN total of this batch's recon rows -- includes
    #: credit-side adjustments, which the selection rule does not constrain.
    credit_total: int
    debit_total: int
    payout: int
    ambiguous: bool
    tying_decompositions: list[tuple[str, ...]]
    #: True when more than `tie_limit` subsets tie and enumeration stopped.
    #: The register below is then a SAMPLE, not the complete set.
    tying_decompositions_truncated: bool
    #: True when the eligible pool exceeded `max_pool` and the batch fell back
    #: to the FIFO reading. Such a batch was NOT solved exactly.
    selection_degraded: bool
    #: size of the eligible pool the rule was applied to
    pool_size: int


@dataclass
class SimulationResult:
    batches: list[Batch]
    #: entity_id -> settlement_id for everything that settled
    settled_in: dict[str, str]
    #: entity_id -> reason, for everything that did not settle
    unsettled_reason: dict[str, str]
    #: payment ids netted out by a full pre-eligibility refund
    netted_out: set[str]


def simulate(
    payments: Sequence[PaymentEvent],
    refunds: Sequence[RefundEvent],
    adjustments: Sequence[AdjustmentEvent],
    config: SimulatorConfig,
    id_maker=None,
) -> SimulationResult:
    """Run the batching rule of SETTLEMENT_SPEC.md sec 1.2 over a ledger."""
    payments = sorted(payments, key=lambda p: (p.created_at, p.id))
    refunds = sorted(refunds, key=lambda r: (r.created_at, r.id))
    adjustments = sorted(adjustments, key=lambda a: (a.created_at, a.id))

    by_id = {p.id: p for p in payments}
    eligible_at = {
        p.id: add_working_days(
            p.created_at, config.settlement_delay_working_days, config.cutoff_hour
        )
        for p in payments
    }

    refunds_for: dict[str, list[RefundEvent]] = {}
    for r in refunds:
        refunds_for.setdefault(r.payment_id, []).append(r)

    # A payment fully refunded before it ever became eligible nets to zero and
    # never settles; neither does the refund. SETTLEMENT_SPEC.md sec 3.
    netted_out: set[str] = set()
    netted_refunds: set[str] = set()
    for p in payments:
        rs = refunds_for.get(p.id, [])
        if not rs:
            continue
        if sum(r.amount for r in rs) == p.amount and all(
            r.created_at <= eligible_at[p.id] for r in rs
        ):
            netted_out.add(p.id)
            netted_refunds.update(r.id for r in rs)

    settled_in: dict[str, str] = {}
    batches: list[Batch] = []
    deferred_debits: set[str] = set()

    def on_hold(p: PaymentEvent, t: int) -> bool:
        if p.hold_from is None or t < p.hold_from:
            return False
        return p.hold_until is None or t < p.hold_until

    debit_events: list[tuple[str, int, int]] = [  # (id, amount, created_at)
        (r.id, r.amount, r.created_at) for r in refunds if r.id not in netted_refunds
    ] + [
        (a.id, a.amount if a.direction == "debit" else -a.amount, a.created_at)
        for a in adjustments
    ]
    debit_by_id = {d[0]: d for d in debit_events}

    for index, t in enumerate(sorted(config.batch_times)):
        # live balance: every unsettled, captured, not-held payment of ANY age
        available = sum(
            p.credit
            for p in payments
            if p.captured
            and p.created_at <= t
            and p.id not in settled_in
            and p.id not in netted_out
            and not on_hold(p, t)
        )
        pending = sorted(
            (d for d in debit_events if d[2] <= t and d[0] not in settled_in),
            key=lambda d: (d[2], d[0]),
        )
        available -= sum(d[1] for d in pending)

        pool = [
            (p.id, p.credit)
            for p in payments
            if p.captured
            and p.id not in settled_in
            and p.id not in netted_out
            and not on_hold(p, t)
            and eligible_at[p.id] <= t
        ]
        # oldest first if the pool must be truncated: FIFO is the only
        # defensible truncation and it is asserted never to trigger in tests
        pool.sort(key=lambda kv: (by_id[kv[0]].created_at, kv[0]))
        # Exact enumeration is exponential. Above `max_pool` it stops being
        # the right algorithm, and a real settlement service at merchant scale
        # is above it every day. Rather than raise -- which would pretend the
        # case does not arise -- degrade to the FIFO reading and RECORD the
        # degradation, so a consumer of this data knows which batches were not
        # solved exactly. See SETTLEMENT_SPEC.md sec 1.5.
        degraded = len(pool) > config.max_pool
        select = (fifo_under_cap if degraded
                  else SELECTION_RULES[config.selection_rule])
        best, winners, truncated = select(pool, max(available, 0))
        chosen = winners[0] if winners else ()

        debits = list(pending)

        def split(items):
            """Credit-side adjustments are negative debits internally, but
            they occupy the `credit` column of a recon row. Report the split
            the way the rows do, so batch totals reconcile field-by-field."""
            positive = sum(d[1] for d in items if d[1] > 0)
            negative = sum(-d[1] for d in items if d[1] < 0)
            return best + negative, positive

        credit_total, debit_total = split(debits)
        # non-negative payout: defer debits largest-first (sec 1.4)
        while debits and credit_total - debit_total < 0:
            debits.sort(key=lambda d: (-d[1], d[0]))
            dropped = debits.pop(0)
            deferred_debits.add(dropped[0])
            credit_total, debit_total = split(debits)
        if credit_total - debit_total < 0:
            continue  # batch cannot form

        if not chosen and not debits:
            continue  # nothing to settle

        settlement_id = (
            id_maker("setl") if id_maker else f"setl_{index:014d}"
        )
        utr = f"{t}{settlement_id[-6:]}"
        for entity_id in chosen:
            settled_in[entity_id] = settlement_id
        for d in debits:
            settled_in[d[0]] = settlement_id

        batches.append(
            Batch(
                settlement_id=settlement_id,
                utr=utr,
                formed_at=t,
                available=available,
                credit_ids=tuple(sorted(chosen)),
                debit_ids=tuple(sorted(d[0] for d in debits)),
                selected_credit=best,
                credit_total=credit_total,
                debit_total=debit_total,
                payout=credit_total - debit_total,
                ambiguous=len(winners) > 1 or truncated,
                tying_decompositions=[tuple(w) for w in winners],
                tying_decompositions_truncated=truncated,
                selection_degraded=degraded,
                pool_size=len(pool),
            )
        )

    unsettled_reason: dict[str, str] = {}
    horizon = max(config.batch_times)
    for p in payments:
        if p.id in settled_in:
            continue
        if not p.captured:
            unsettled_reason[p.id] = "not_captured"
        elif p.id in netted_out:
            unsettled_reason[p.id] = "netted_out_by_full_refund"
        elif on_hold(p, horizon):
            unsettled_reason[p.id] = "on_hold_dispute"
        elif eligible_at[p.id] > horizon:
            unsettled_reason[p.id] = "not_yet_eligible_at_horizon"
        else:
            unsettled_reason[p.id] = "rolled_forward_past_horizon"
    for r in refunds:
        if r.id in settled_in:
            continue
        unsettled_reason[r.id] = (
            "netted_out_by_full_refund" if r.id in netted_refunds
            else "debit_deferred_past_horizon"
        )
    for a in adjustments:
        if a.id not in settled_in:
            unsettled_reason[a.id] = "debit_deferred_past_horizon"

    return SimulationResult(
        batches=batches,
        settled_in=settled_in,
        unsettled_reason=unsettled_reason,
        netted_out=netted_out,
    )
