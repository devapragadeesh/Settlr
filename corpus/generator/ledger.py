"""The organic ledger draw. Defect D5's fix, and D6's and D7's.

## D5: calibration by SELECTION, never by MINTING

The frozen generator minted rows to force arithmetic:
`plant_ambiguity` / `plant_pressure` / `_insert_debit` inserted large debit
adjustments whose only purpose was to close a gap. They are findable, and the
leak is worse than the description string:

    filter                                     finds
    debit adjustment, dispute_id null, >12000  batches {1, 3, 9}
    ...and the provably-ambiguous batches are  {3, 9}

    the 4 minted debits:      1,200,573 .. 3,295,351 paise
    every organic adjustment:     3,195 ..    39,197 paise

**Perfect separation on the `amount` column alone**, before reading a single
description. That is the third leak of this shape after `source_ref` and
`notes.reason`, and it generalises: *any row minted to make arithmetic work
will leak, in some coordinate, whether or not anyone anticipated which.*

### The lever is the ledger draw, not the batch

Batch composition is DETERMINED by the selection rule given the ledger. You
cannot "choose which organic rows go in a batch" without changing the rule. So
the only honest lever is the draw itself -- and rejection-sampling amounts
until a tie appears is **D5 in a new coordinate**: it conditions the amount
distribution on a subset-sum coincidence, localised to the window where the
tie was wanted, which is exactly the elevated-partial-sum-equality signature
`corpus/leakage_audit.py` hunts.

So ties are a **consequence**, not a target:

* every amount in the ledger is drawn from a **price lattice** -- real
  merchant SKUs cluster on price points crossed with a quantity and a
  shipping line, which is *more* realistic than a continuous draw, not less;
* multi-closure then arises naturally at larger pools in **every** batch, with
  no per-batch conditioning and no local signature;
* `k` is measured post-hoc by `closure.py` and recorded. Ambiguity is
  `planted: false` **everywhere** in this corpus, by construction.

Every adjustment is a real business event with a real cause: a lost-dispute
clawback ties to a dispute's `amount_deducted`, a fee reversal ties to an
actual overcharge computed from the payment it reverses. **No row exists whose
only purpose is arithmetic.**

## D6: interleave everything

Orphan invoices are allocated slots uniformly across the whole invoice
sequence *before* any invoice is issued, so they hold ordinary numbers. In the
frozen set they hold 1179-1184 -- the six highest in a file otherwise monotone
in date order -- which a rank check finds at precision 1.000 even though a
file-position check passes.

The gateway's supplier invoices use the same neutral series as every other
vendor, so identifying the supplier requires reconciling fee totals
month-by-month rather than grepping `RZP/BLR/`.

## D7: decoys collide on CREDIT

Settlement arithmetic runs on `credit = amount - fee`, not on `amount`. The
frozen decoy class equalises `amount` across a pair with different MDR tiers,
so their credits differ and no ambiguity is created. Measured: 3 of the 4
frozen pairs differ in credit by 3,670 to 11,732 paise; the one pair that does
collide does so **by accident**, alongside three non-decoy pairs that collide
for the same reason.

Here the collision is solved for directly: given the partner's tier, scan for
the amount whose `compute_fee`-derived credit equals the target credit exactly.
Near-collisions of 1-2 paise fall out of the same scan and exercise tolerance
boundaries. If no amount in a sane range achieves it for that tier pair, the
plant is recorded `planted: false` with the tier pair as the reason -- the fee
is never adjusted to force it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Sequence

from engine.simulator import (IST, AdjustmentEvent, PaymentEvent, RefundEvent,
                              compute_fee)

__all__ = ["LedgerSpec", "Ledger", "build_ledger", "PRICE_LATTICE",
           "make_id_factory", "solve_credit_collision"]


# --------------------------------------------------------------------------
# the price lattice
# --------------------------------------------------------------------------

def _lattice() -> tuple[int, ...]:
    """Price points in paise. A merchant sells SKUs, not uniform random reals.

    Deliberately a lattice and deliberately not conditioned on anything: base
    price points at 50-rupee steps, psychological price points, and larger
    tickets -- crossed with a small quantity multiplier and an optional
    shipping line, because an order is line items rather than a single SKU.

    ## Why the granularity is a calibrated parameter, and what it was
    ## calibrated against

    The first draft used the 145 base points alone. Measured on 262 payments
    that gave 114 distinct amounts and 66 duplicated CREDIT values, and
    duplicate credits are swap-equivalent inside a batch, so closure counts
    exploded: at pool ~20, **11 of 12 credits had multiple closing subsets and
    7 of 12 exceeded 500**. That corpus sits entirely ABOVE the hard regime,
    which is the mirror image of the frozen set's flaw of sitting entirely
    below it, and it collapses axis A -- every pool size looks the same.

    So the lattice is calibrated to make axis A **discriminate**, against
    measured closure counts, **before any resolver exists**. Nothing about
    resolver performance is observable at the time it is picked, which is the
    same ordering discipline `phi` and the seeds are held to, and it is
    recorded here rather than adjusted quietly.

    What is NOT done, and is the whole point of D5: no per-batch conditioning,
    no rejection sampling against a target, no amount chosen to make a sum
    work. The distribution is global, and whatever closure counts fall out of
    it are measured and reported.
    """
    base: list[int] = []
    base += [rupees * 100 for rupees in range(250, 5_001, 50)]
    base += [rupees * 100 for rupees in (299, 499, 799, 999, 1_299, 1_499,
                                         1_999, 2_499, 2_999, 4_999)]
    base += [rupees * 100 for rupees in range(6_000, 25_001, 500)]
    points: set[int] = set()
    for price in base:
        for quantity in (1, 2, 3, 4):
            for shipping in (0, 4_900, 9_900, 14_900):
                points.add(price * quantity + shipping)
    return tuple(sorted(points))


PRICE_LATTICE = _lattice()

def _draw_amount(rng: random.Random) -> int:
    """Draw from the lattice with a realistic long tail.

    Small tickets dominate an Indian retail book; large ones are rare and are
    what make a batch's arithmetic interesting. Weighting by position rather
    than sampling uniformly keeps that shape without leaving the lattice.
    """
    if rng.random() < 0.72:
        return rng.choice(PRICE_LATTICE[:len(PRICE_LATTICE) // 2])
    return rng.choice(PRICE_LATTICE[len(PRICE_LATTICE) // 2:])


BANKS = ["ALLA", "CBIN", "CNRB", "CSBK", "DCBL", "BARB_R", "DEUT", "UTIB",
         "ICIC", "SBIN"]
WALLETS = ["airtelmoney", "mobikwik", "olamoney"]
CARD_NETWORKS = ["Visa", "MasterCard", "RuPay", "Amex"]
CARD_ISSUERS = ["HDFC", "ICIC", "SBIN", "KARB", "UTIB", "AXIS"]
CARD_TYPES = ["credit", "debit"]

#: `notes` keys and their value pools. Both keys AND values are shared across
#: every class -- a `(key, value)` pair was a 100%-precision marker once
#: already (SETTLEMENT_SPEC.md 8.1), so nothing here is class-conditional.
NOTE_KEYS = [
    ("warehouse", ["BLR-1", "BLR-2", "HYD-1", "NCR-3", "MAA-1"]),
    ("customer_segment", ["retail", "b2b", "wholesale", "marketplace"]),
    ("channel", ["web", "ios", "android", "pos"]),
    ("cart_id", []),
]

#: Refund reasons. ONE pool, drawn from identically regardless of what the
#: refund is for -- the frozen set used a disjoint list for calibration
#: refunds and `grep partial_cancellation` found every calibrated batch.
REFUND_REASONS = ["customer_cancelled", "item_out_of_stock",
                  "damaged_in_transit", "size_exchange", "delivery_delayed",
                  "partial_cancellation", "duplicate_order", "quality_issue"]

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def make_id_factory(rng: random.Random):
    """Razorpay-shaped ids carrying no information.

    Asserted by the leakage audit rather than by assumption: an id that encodes
    anything is a separator, and the audit tests id ordinals explicitly.
    """
    seen: set[str] = set()

    def make(prefix: str) -> str:
        while True:
            body = "".join(rng.choice(ALPHABET) for _ in range(14))
            candidate = f"{prefix}_{body}"
            if candidate not in seen:
                seen.add(candidate)
                return candidate

    return make


# --------------------------------------------------------------------------
# D7: solve for a credit collision instead of forcing one
# --------------------------------------------------------------------------


def solve_credit_collision(
    target_credit: int, method: str, card_network: str | None,
    card_type: str | None, *, delta: int = 0,
    search: range | None = None,
) -> int | None:
    """The amount whose `credit` under this tier equals `target_credit + delta`.

    Exact integer scan over `compute_fee`; no fee is ever adjusted to force the
    result. Returns None when the tier pair cannot reach it, which is recorded
    as `planted: false` rather than fixed.
    """
    wanted = target_credit + delta
    lo = wanted
    hi = int(wanted * 1.10) + 200
    for amount in (search or range(lo, hi + 1)):
        fee, _tax = compute_fee(amount, method, card_network, card_type)
        if amount - fee == wanted:
            return amount
    return None


# --------------------------------------------------------------------------
# spec and result
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerSpec:
    """Everything about the draw. Pool size is controlled HERE -- upstream, by
    arrival volume and batch cadence -- and never by a minted row downstream.
    """

    window_start: datetime
    window_end: datetime
    payments: int
    #: fractions of `payments`, not absolute counts, so the mix is stable as
    #: volume is scaled to hit an axis-A pool target
    full_refund_pre: float = 0.025
    partial_refund_pre: float = 0.025
    refund_later: float = 0.025
    dispute_held: float = 0.020
    dispute_won: float = 0.020
    dispute_lost: float = 0.020
    failed: float = 0.020
    extra_refunds: float = 0.05
    goodwill_credits: float = 0.02
    fee_reversals: float = 0.02
    decoy_pairs: int = 6
    near_collision_pairs: int = 3
    #: Raised from 3 after the leak audit: with only 3 pairs, ONE pair is 33%
    #: of the class and TWO are 67%, so a predicate keying on a single shared
    #: (amount, issuer) value cleared the 50% recall bar by coincidence. A
    #: duplicate is DEFINED by sharing values with its twin, so the class is
    #: inherently somewhat self-identifying; the fix is to make the class large
    #: enough that no single value predicate covers half of it.
    duplicate_rows: int = 10


@dataclass
class Ledger:
    payments: list[PaymentEvent]
    refunds: list[RefundEvent]
    adjustments: list[AdjustmentEvent]
    roles: dict[str, str]
    disputes: list[dict]
    #: name -> {"planted": bool, "members": [...], "reason": str}
    classes: dict[str, dict] = field(default_factory=dict)


def _ts(when: datetime) -> int:
    return int(when.timestamp())


def _pick_method(rng: random.Random) -> str:
    return rng.choices(["upi", "netbanking", "card", "wallet"],
                       weights=[40, 27, 24, 9], k=1)[0]


def _instrument(rng: random.Random, method: str):
    network = issuer = card_type = bank = wallet = None
    if method == "card":
        network = rng.choice(CARD_NETWORKS)
        issuer = rng.choice(CARD_ISSUERS)
        card_type = rng.choice(CARD_TYPES)
    elif method == "netbanking":
        bank = rng.choice(BANKS)
    elif method == "wallet":
        wallet = rng.choice(WALLETS)
    return network, issuer, card_type, bank, wallet


def _notes(rng: random.Random, order_no: int):
    """`{}` when populated, `[]` when empty -- never null, never a string."""
    if rng.random() < 0.12:
        return []
    note: dict = {}
    for key, choices in rng.sample(NOTE_KEYS, k=rng.randint(1, 2)):
        note[key] = rng.choice(choices) if choices else f"crt_{order_no:06d}"
    return note


def build_ledger(rng: random.Random, mk, spec: LedgerSpec) -> Ledger:
    """Draw an organic ledger. No row exists whose only purpose is arithmetic."""
    payments: list[PaymentEvent] = []
    refunds: list[RefundEvent] = []
    adjustments: list[AdjustmentEvent] = []
    roles: dict[str, str] = {}
    disputes: list[dict] = []
    classes: dict[str, dict] = {}

    def count(fraction: float) -> int:
        return max(1, round(spec.payments * fraction)) if fraction else 0

    roster: list[str] = []
    for role, number in (("full_refund_pre", count(spec.full_refund_pre)),
                         ("partial_refund_pre", count(spec.partial_refund_pre)),
                         ("refund_later", count(spec.refund_later)),
                         ("dispute_held", count(spec.dispute_held)),
                         ("dispute_won", count(spec.dispute_won)),
                         ("dispute_lost", count(spec.dispute_lost)),
                         ("failed", count(spec.failed))):
        roster.extend([role] * number)
    roster.extend(["clean"] * max(0, spec.payments - len(roster)))
    rng.shuffle(roster)

    span = int((spec.window_end - spec.window_start).total_seconds())
    start = _ts(spec.window_start)
    order_no = 40000

    for role in roster:
        order_no += 1
        method = _pick_method(rng)
        network, issuer, card_type, _bank, _wallet = _instrument(rng, method)
        amount = _draw_amount(rng)
        captured = role != "failed"
        # `tax: 0` shape of Razorpay's published recon sample -- the row on
        # which the two candidate fee identities are indistinguishable.
        gst_applies = rng.random() > 0.03
        if captured:
            fee, tax = compute_fee(amount, method, network, card_type, gst_applies)
        else:
            fee = tax = None            # failed payments carry null, NOT 0
        created = start + rng.randrange(span)

        hold_from = hold_until = None
        dispute_id = None
        if role in ("dispute_held", "dispute_won"):
            # opens INSIDE the T+2 window, so the hold can actually withhold
            dispute_id = mk("disp")
            hold_from = created + rng.randrange(3600, 36 * 3600)
            if role == "dispute_won":
                hold_until = hold_from + rng.randrange(18, 46) * 86400
            disputes.append({
                "id": dispute_id, "phase": rng.choice(["retrieval", "fraud"]),
                "status": "won" if role == "dispute_won" else "under_review",
                "opened_at": hold_from, "amount_deducted": 0})
        elif role == "dispute_lost":
            # a real chargeback arrives AFTER the payment was paid out, and
            # claws back through a debit adjustment
            dispute_id = mk("disp")
            disputes.append({
                "id": dispute_id, "phase": "chargeback", "status": "lost",
                "opened_at": created + rng.randrange(20, 46) * 86400,
                "amount_deducted": amount})

        payment = PaymentEvent(
            id=mk("pay"), order_id=mk("order"),
            order_receipt=f"rcpt-{order_no}", amount=amount, fee=fee, tax=tax,
            method=method, created_at=created, captured=captured,
            notes=_notes(rng, order_no),
            description="Order payment" if captured else None,
            card_network=network, card_issuer=issuer, card_type=card_type,
            dispute_id=dispute_id, hold_from=hold_from, hold_until=hold_until,
            source_tier="synthesized_modelled",
            source_ref=SOURCE_REF)
        payments.append(payment)
        roles[payment.id] = role

        if role == "full_refund_pre":
            refunds.append(RefundEvent(
                id=mk("rfnd"), payment_id=payment.id, amount=amount,
                created_at=created + rng.randrange(3600, 30 * 3600),
                notes={"reason": rng.choice(REFUND_REASONS)},
                source_tier="synthesized_modelled", source_ref=SOURCE_REF))
        elif role == "partial_refund_pre":
            refunds.append(RefundEvent(
                id=mk("rfnd"), payment_id=payment.id,
                amount=max(100, (amount // rng.randint(2, 5)) // 100 * 100),
                created_at=created + rng.randrange(3600, 30 * 3600),
                notes={"reason": rng.choice(REFUND_REASONS)},
                source_tier="synthesized_modelled", source_ref=SOURCE_REF))
        elif role == "refund_later":
            refunds.append(RefundEvent(
                id=mk("rfnd"), payment_id=payment.id,
                amount=max(100, (amount // rng.randint(2, 4)) // 100 * 100),
                created_at=created + rng.randrange(6, 30) * 86400,
                notes={"reason": rng.choice(REFUND_REASONS)},
                source_tier="synthesized_modelled", source_ref=SOURCE_REF))
        elif role == "dispute_lost":
            # THE CAUSE IS THE DISPUTE. The amount is the dispute's
            # amount_deducted, not a number chosen to close a gap.
            adjustments.append(AdjustmentEvent(
                id=mk("adj"), amount=amount,
                created_at=created + rng.randrange(22, 50) * 86400,
                description=f"Chargeback debit - reason {rng.choice(['4863', '13.1', '10.4', '12.5'])}",
                direction="debit", dispute_id=dispute_id,
                source_tier="synthesized_modelled", source_ref=SOURCE_REF))

    settled_pool = [p for p in payments if p.captured and p.fee]

    for _ in range(count(spec.extra_refunds)):
        parent = rng.choice(settled_pool)
        refunds.append(RefundEvent(
            id=mk("rfnd"), payment_id=parent.id,
            amount=max(100, (parent.amount // rng.randint(2, 6)) // 100 * 100),
            created_at=parent.created_at + rng.randrange(2, 34) * 86400,
            notes={"reason": rng.choice(REFUND_REASONS)},
            source_tier="synthesized_modelled", source_ref=SOURCE_REF))

    # --- credit-side adjustments, each with a real cause -------------------
    for _ in range(count(spec.goodwill_credits)):
        adjustments.append(AdjustmentEvent(
            id=mk("adj"), amount=rng.choice([50000, 100000, 150000, 200000]),
            created_at=start + rng.randrange(span),
            description="Goodwill credit - service disruption",
            direction="credit", source_tier="synthesized_modelled",
            source_ref=SOURCE_REF))

    for _ in range(count(spec.fee_reversals)):
        # THE CAUSE IS AN ACTUAL OVERCHARGE: the difference between the fee
        # billed at the card rate and the fee that should have applied.
        overcharged = rng.choice([p for p in settled_pool if p.method == "card"]
                                 or settled_pool)
        billed, _ = compute_fee(overcharged.amount, "card", "Amex", "credit")
        correct, _ = compute_fee(overcharged.amount, "card", "Visa", "credit")
        delta = abs(billed - correct)
        if delta <= 0:
            continue
        adjustments.append(AdjustmentEvent(
            id=mk("adj"), amount=delta,
            created_at=overcharged.created_at + rng.randrange(5, 40) * 86400,
            description="Fee reversal - overcharged MDR", direction="credit",
            source_tier="synthesized_modelled", source_ref=SOURCE_REF))

    classes.update(_plant_decoys(rng, mk, payments, roles, spec, start, span))
    classes.update(_plant_duplicates(rng, mk, payments, roles, spec))

    return Ledger(payments=payments, refunds=refunds, adjustments=adjustments,
                  roles=roles, disputes=disputes, classes=classes)


#: ONE provenance string for every row in the corpus.
#:
#: The frozen set's `source_ref` is still a class marker despite
#: SETTLEMENT_SPEC.md 8.1 stating it is not:
#:   'recon sample adj_EhcHONhX4ChgNC shape' -> c09_lost_dispute_adjustment,
#:                                              precision 1.00, recall 1.00
#: A provenance field that varies by what the generator was doing is a stage
#: direction, and stage directions leak. So it does not vary. The provenance
#: that genuinely differs per row lives in the ground-truth key, where a
#: solver cannot read it.
SOURCE_REF = "corpus/CORPUS_SPEC.md; see ground truth for per-row provenance"


def _plant_decoys(rng, mk, payments, roles, spec: LedgerSpec, start, span):
    """D7: pairs colliding on CREDIT, plus 1-2 paise near-collisions."""
    exact: list[list[str]] = []
    near: list[dict] = []
    failures: list[dict] = []
    candidates = [p for p in payments if p.captured and p.fee]
    if not candidates:
        return {}

    wanted = spec.decoy_pairs + spec.near_collision_pairs
    for index in range(wanted):
        partner = rng.choice(candidates)
        delta = 0 if index < spec.decoy_pairs else rng.choice([1, 2])
        method = _pick_method(rng)
        network, issuer, card_type, _b, _w = _instrument(rng, method)
        amount = solve_credit_collision(
            partner.amount - partner.fee, method, network, card_type,
            delta=delta)
        if amount is None:
            failures.append({
                "planted": False,
                "reason": f"no amount under ({method}, {network}, {card_type}) "
                          f"yields credit {partner.amount - partner.fee}+{delta}"})
            continue
        fee, tax = compute_fee(amount, method, network, card_type)
        twin = PaymentEvent(
            id=mk("pay"), order_id=mk("order"),
            order_receipt=f"rcpt-{rng.randrange(40000, 49999)}",
            amount=amount, fee=fee, tax=tax, method=method,
            # SAME DAY as its partner, different second -- the collision must
            # be in the settled figure, and the timing must not be a marker.
            created_at=partner.created_at + rng.randrange(-6, 7) * 3600,
            captured=True, notes=_notes(rng, rng.randrange(40000, 49999)),
            description="Order payment", card_network=network,
            card_issuer=issuer, card_type=card_type,
            source_tier="synthesized_modelled", source_ref=SOURCE_REF)
        payments.append(twin)
        roles[twin.id] = "clean"
        if delta == 0:
            exact.append(sorted([partner.id, twin.id]))
        else:
            near.append({"pair": sorted([partner.id, twin.id]), "delta": delta})

    out = {
        "d07_decoy_credit_collision": {
            "planted": bool(exact), "table": "recon",
            "members": sorted({pid for pair in exact for pid in pair}),
            "pairs": exact,
            "reason": "" if exact else "no tier pair reached an exact collision"},
        "d07_decoy_credit_near_collision": {
            "planted": bool(near), "table": "recon",
            "members": sorted({pid for item in near for pid in item["pair"]}),
            "pairs": near},
    }
    if failures:
        out["d07_decoy_failures"] = {"planted": False, "table": "recon",
                                     "members": [], "failures": failures}
    return out


def _plant_duplicates(rng, mk, payments, roles, spec: LedgerSpec):
    """Same credit, same day, different ids. A real merchant double-submits."""
    made: list[list[str]] = []
    candidates = [p for p in payments if p.captured and p.fee]
    for _ in range(spec.duplicate_rows):
        if not candidates:
            break
        original = rng.choice(candidates)
        twin = PaymentEvent(
            id=mk("pay"), order_id=mk("order"),
            order_receipt=f"rcpt-{rng.randrange(40000, 49999)}",
            amount=original.amount, fee=original.fee, tax=original.tax,
            method=original.method,
            created_at=original.created_at + rng.randrange(60, 3600),
            captured=True, notes=_notes(rng, rng.randrange(40000, 49999)),
            description="Order payment", card_network=original.card_network,
            card_issuer=original.card_issuer, card_type=original.card_type,
            source_tier="synthesized_modelled", source_ref=SOURCE_REF)
        payments.append(twin)
        roles[twin.id] = "clean"
        made.append(sorted([original.id, twin.id]))
    return {"d08_duplicate_payment_rows": {
        "planted": bool(made), "table": "recon",
        "members": sorted({pid for pair in made for pid in pair}),
        "pairs": made}}
