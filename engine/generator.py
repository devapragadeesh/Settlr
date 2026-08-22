"""Deterministic generator for the Settlement Truth Engine dataset.

Emits the solver-visible dataset, the isolated ground-truth key, and the
companion ERP / bank / GST files. Contains NO matching or solving logic.

Run:  python3 engine/generator.py [--seed 20260822] [--out engine/data]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

from simulator import (
    IST,
    ceil_div,
    AdjustmentEvent,
    PaymentEvent,
    RefundEvent,
    SimulatorConfig,
    add_working_days,
    compute_fee,
    simulate,
)

ROOT = Path(__file__).resolve().parent
CAPTURED = ROOT.parent / "spike" / "captured_dataset.json"

B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# --- window and cadence (SETTLEMENT_SPEC.md sec 1; operator choice) ---------
WINDOW_START = datetime(2026, 6, 15, 0, 0, tzinfo=IST)
WINDOW_END = datetime(2026, 8, 28, 23, 59, tzinfo=IST)
#: 12 weekly Wednesday 17:00 IST cut-offs, 2026-06-17 .. 2026-09-02
BATCH_DATES = [datetime(2026, 6, 17, 17, 0, tzinfo=IST) + timedelta(weeks=i) for i in range(12)]

MERCHANT_GSTIN_STATE = "29"  # Karnataka -> CGST+SGST on Razorpay's fee invoice

BANKS = ["ALLA", "CBIN", "CNRB", "CSBK", "DCBL", "BARB_R", "DEUT", "UTIB", "ICIC", "SBIN"]
WALLETS = ["airtelmoney", "mobikwik", "olamoney"]
CARD_NETWORKS = ["Visa", "MasterCard", "RuPay", "Amex"]
CARD_ISSUERS = ["HDFC", "ICIC", "SBIN", "KARB", "UTIB", "AXIS"]
CARD_TYPES = ["credit", "debit"]

NOTE_KEYS = [
    ("channel", ["web", "ios", "android", "pos"]),
    ("cart_id", None),
    ("customer_segment", ["retail", "b2b", "subscription", "marketplace"]),
    ("warehouse", ["BLR-1", "BLR-2", "HYD-1", "NCR-3"]),
]

#: One pool, used by organic AND calibration refunds alike. A reason value
#: unique to calibration debits would be a 100%-precision grep for "this batch
#: had its live-balance cap deliberately tuned".
REFUND_REASONS = ["customer_cancelled", "item_out_of_stock", "damaged_in_transit",
                  "duplicate_charge", "size_exchange", "partial_cancellation"]

VENDOR_NAMES = [
    "CLOUDSPINE TECHNOLOGIES", "NIMBUS LOGISTICS", "ARCLIGHT MEDIA",
    "VERDANT PACKAGING", "SIXTHLANE ANALYTICS", "TOLLGATE FACILITIES",
]


# --- deterministic id + gstin helpers --------------------------------------


def make_id_factory(rng: random.Random):
    seen: set[str] = set()

    def make(prefix: str) -> str:
        while True:
            body = "".join(rng.choice(B62) for _ in range(14))
            candidate = f"{prefix}_{body}"
            if candidate not in seen:
                seen.add(candidate)
                return candidate

    return make


def gstin_checksum(first14: str) -> str:
    """Standard GSTIN mod-36 check character."""
    total = 0
    for i, ch in enumerate(first14):
        value = int(ch) if ch.isdigit() else 10 + ord(ch) - ord("A")
        factor = 2 if i % 2 else 1
        product = value * factor
        total += product // 36 + product % 36
    return "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[(36 - total % 36) % 36]


#: PAN's 4th character encodes the holder's entity type. `X` is not in the
#: issued set, so a PAN carrying it cannot exist -- which makes it impossible
#: for a generated GSTIN to collide with a real registration. This is a
#: construction guarantee, not luck.
PAN_ENTITY_CHARS = "ABCFGHLJPTKE"
UNISSUABLE_ENTITY_CHAR = "X"
assert UNISSUABLE_ENTITY_CHAR not in PAN_ENTITY_CHARS

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def make_gstin(rng: random.Random, state: str | None = None) -> str:
    """Emit a checksum-valid but deliberately UNISSUABLE GSTIN."""
    state = state or f"{rng.randint(1, 37):02d}"
    pan = (
        "".join(rng.choice(LETTERS) for _ in range(3))
        + UNISSUABLE_ENTITY_CHAR
        + rng.choice(LETTERS)
        + f"{rng.randint(0, 9999):04d}"
        + rng.choice(LETTERS)
    )
    first14 = f"{state}{pan}1Z"
    return first14 + gstin_checksum(first14)


def rupees(paise: int) -> str:
    """Format integer paise as a rupee string. No float arithmetic."""
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}{whole}.{frac:02d}"


def ts(dt: datetime) -> int:
    return int(dt.timestamp())


def iso_date(unix_ts: int) -> str:
    return datetime.fromtimestamp(unix_ts, IST).strftime("%Y-%m-%d")


# --- population design -----------------------------------------------------

#: role -> count. Roles drive construction; final class labels are derived
#: from what the simulator ACTUALLY did, not from the role.
ROLES = OrderedDict(
    [
        ("clean", 165),
        ("full_refund_pre", 5),
        ("partial_refund_pre", 5),
        ("refund_later", 5),
        ("dispute_held", 4),
        ("dispute_won", 4),
        ("dispute_lost", 4),
        ("failed", 4),
    ]
)
EXTRA_REFUNDS = 10
MISC_ADJUSTMENTS = 8
#: pairs of payments with the SAME amount on the SAME day. A matcher keying on
#: (amount, date) alone must not be able to tell them apart -- these are the
#: decoys that punish a lazy fuzzy join.
DECOY_PAIRS = 4
#: index of the batch given a debit large enough to force debit deferral
NEGATIVE_BALANCE_BATCH = 0
AMBIGUITY_BATCHES = [3, 6, 9]
#: batches deliberately put under balance pressure so eligible payments are
#: EXCLUDED and roll forward -- Razorpay's documented partial-settlement case.
PRESSURE_BATCHES = [1, 3, 6, 9, 10]
#: subset of the above where the excluded set must be MULTI-payment, so the
#: selection is not solvable by "drop the single largest that does not fit".
DEEP_PRESSURE_BATCHES = {3, 9}


def load_templates() -> list[dict]:
    data = json.loads(CAPTURED.read_text())
    return sorted(data["payments"], key=lambda p: p["id"])


def pick_method(rng: random.Random) -> str:
    """UPI-dominant by count, as an Indian merchant book is in 2026.

    The captured account produced netbanking x9 and wallet x3 only -- card was
    WAF-blocked on the ajax path and UPI was disabled account-side -- so the
    mix here is modelled, not observed.
    """
    return rng.choices(
        ["upi", "netbanking", "card", "wallet"], weights=[40, 27, 24, 9], k=1
    )[0]


def pick_amount(rng: random.Random, templates: list[dict]) -> int:
    """Amounts anchored on the real captured spread, in paise."""
    style = rng.random()
    if style < 0.30:
        base = rng.choice(templates)["amount"]
        return max(10000, base + rng.randrange(-40, 41) * 100)
    if style < 0.65:
        return rng.randrange(500, 9000) * 100          # round rupee amounts
    if style < 0.90:
        return rng.randrange(50000, 900000)            # arbitrary paise
    return rng.randrange(900000, 2500000)              # large tickets


def make_notes(rng: random.Random, order_no: int) -> dict | list:
    """`{}` when populated, `[]` when empty -- never null, never a string."""
    if rng.random() < 0.12:
        return []
    note: dict = {}
    for key, choices in rng.sample(NOTE_KEYS, k=rng.randint(1, 2)):
        note[key] = rng.choice(choices) if choices else f"crt_{order_no:06d}"
    return note


def build_ledger(rng: random.Random, mk):
    templates = load_templates()
    fee_bearing = [t for t in templates if t["fee"] is not None]

    payments: list[PaymentEvent] = []
    refunds: list[RefundEvent] = []
    adjustments: list[AdjustmentEvent] = []
    roles: dict[str, str] = {}

    roster: list[str] = []
    for role, count in ROLES.items():
        roster.extend([role] * count)
    rng.shuffle(roster)

    span = int((WINDOW_END - WINDOW_START).total_seconds())
    order_no = 40000
    mirror_queue = list(fee_bearing)
    mirrored_ids: set[str] = set()

    for index, role in enumerate(roster):
        order_no += 1
        mirrored = None
        if role == "clean" and mirror_queue and index % 11 == 0:
            mirrored = mirror_queue.pop(0)

        network = ctype = None
        if mirrored:
            amount = mirrored["amount"]
            method = mirrored["method"]
            bank = mirrored["bank"]
            wallet = mirrored["wallet"]
            fee, tax = mirrored["fee"], mirrored["tax"]
            tier = "captured_real"
            ref = f"spike/captured_dataset.json::{mirrored['id']}"
            # `notes` TYPE is copied from the captured row; its CONTENT is
            # re-issued, because the captured notes carry spike scenario
            # labels and would leak ground truth.
            notes = make_notes(rng, order_no) if isinstance(mirrored["notes"], dict) else []
            if notes == [] and isinstance(mirrored["notes"], dict):
                notes = {"channel": "web"}
        else:
            amount = pick_amount(rng, templates)
            method = pick_method(rng)
            bank = rng.choice(BANKS) if method == "netbanking" else None
            wallet = rng.choice(WALLETS) if method == "wallet" else None
            network = rng.choice(CARD_NETWORKS) if method == "card" else None
            ctype = rng.choice(CARD_TYPES) if method == "card" else None
            # Razorpay's own published recon sample carries `tax: 0` on its
            # payment row. On such a row `amount - fee` and `amount - fee - tax`
            # are indistinguishable, which is exactly why the wrong identity is
            # easy to adopt. Plant a few so the analyzer must say INDECISIVE.
            gst_applies = rng.random() >= 0.04
            fee, tax = compute_fee(amount, method, network, ctype, gst_applies)
            notes = make_notes(rng, order_no)
            if method in ("card", "upi"):
                tier = "synthesized_modelled"
                ref = ("Razorpay published pricing; method never observed on "
                       "the captured account")
            elif not gst_applies:
                tier = "synthesized_documented"
                ref = "tax:0 shape of Razorpay's published recon sample row"
            else:
                tier = "synthesized_documented"
                ref = "fee model verified 14/14 on captured rows; SETTLEMENT_SPEC.md 4.1"

        created = ts(WINDOW_START) + rng.randrange(span)
        dt = datetime.fromtimestamp(created, IST).replace(
            hour=rng.randint(9, 21), minute=rng.randrange(60), second=rng.randrange(60)
        )
        created = ts(dt)

        pid = mk("pay")
        oid = mk("order")
        captured = role != "failed"
        if not captured:
            fee, tax = None, None

        card_network = card_issuer = card_type = None
        if method == "card":
            card_network = network if not mirrored else rng.choice(CARD_NETWORKS)
            card_issuer = rng.choice(CARD_ISSUERS)
            card_type = ctype if not mirrored else rng.choice(CARD_TYPES)

        payments.append(
            PaymentEvent(
                id=pid,
                order_id=oid,
                order_receipt=None if rng.random() < 0.25 else f"rcpt-{order_no}",
                amount=amount,
                fee=fee,
                tax=tax,
                method=method,
                created_at=created,
                captured=captured,
                notes=notes,
                description=None if rng.random() < 0.7 else "Order payment",
                bank=bank,
                wallet=wallet,
                card_network=card_network,
                card_issuer=card_issuer,
                card_type=card_type,
                source_tier=tier,
                source_ref=ref,
            )
        )
        roles[pid] = role
        if mirrored:
            mirrored_ids.add(pid)

    # --- decoys: same amount, same day, different payment ------------------
    clean_ids = [p.id for p in payments if roles[p.id] == "clean"]
    # A decoy rewrites its TARGET's amount and timestamp. Doing that to a
    # mirrored row would falsify its `captured_real` claim, so mirrored rows
    # may be a decoy's source but never its target.
    target_ids = [pid for pid in clean_ids if pid not in mirrored_ids]
    index_of = {p.id: i for i, p in enumerate(payments)}
    decoys: list[tuple[str, str]] = []
    for source_id, target_id in zip(
            rng.sample(clean_ids, DECOY_PAIRS),
            rng.sample(target_ids[::-1], DECOY_PAIRS)):
        if source_id == target_id:
            continue
        source = payments[index_of[source_id]]
        target = payments[index_of[target_id]]
        same_day = datetime.fromtimestamp(source.created_at, IST).replace(
            hour=rng.randint(9, 21), minute=rng.randrange(60), second=rng.randrange(60))
        fee, tax = compute_fee(source.amount, target.method,
                               target.card_network, target.card_type)
        payments[index_of[target_id]] = PaymentEvent(
            **{**target.__dict__, "amount": source.amount, "fee": fee, "tax": tax,
               "created_at": ts(same_day)})
        decoys.append((source_id, target_id))
    if len(decoys) < DECOY_PAIRS - 1:
        raise ValueError(f"only {len(decoys)} decoy pairs planted; "
                         f"the generator must not silently under-deliver")

    payments.sort(key=lambda p: (p.created_at, p.id))
    elig = {p.id: add_working_days(p.created_at, 2, 17) for p in payments}
    horizon = ts(BATCH_DATES[-1])

    def add_refund(p: PaymentEvent, amount: int, when: int, tier: str, ref: str):
        # every event must fall inside the observation window, or it would not
        # appear in a recon dump for this period at all
        when = max(p.created_at + 60, min(when, horizon - 7200))
        refunds.append(
            RefundEvent(
                id=mk("rfnd"),
                payment_id=p.id,
                amount=amount,
                created_at=when,
                notes=[] if rng.random() < 0.5 else {
                    "reason": rng.choice(REFUND_REASONS)},
                source_tier=tier,
                source_ref=ref,
            )
        )

    doc_ref = "https://razorpay.com/docs/payments/settlements/ (refund reduces live balance)"
    for p in payments:
        role = roles[p.id]
        if role == "full_refund_pre":
            add_refund(p, p.amount, p.created_at + rng.randrange(3600, 36 * 3600),
                       "synthesized_documented", doc_ref)
        elif role == "partial_refund_pre":
            part = max(10000, (p.amount // rng.randint(2, 4)) // 100 * 100)
            add_refund(p, part, p.created_at + rng.randrange(3600, 30 * 3600),
                       "synthesized_documented", doc_ref)
        elif role == "refund_later":
            part = max(10000, (p.amount // rng.randint(2, 3)) // 100 * 100)
            add_refund(p, part, elig[p.id] + rng.randrange(9, 26) * 86400,
                       "synthesized_documented", doc_ref)

    clean_pool = sorted([p for p in payments if roles[p.id] == "clean"], key=lambda p: p.id)
    for p in rng.sample(clean_pool, EXTRA_REFUNDS):
        if rng.random() < 0.45:
            when = p.created_at + rng.randrange(3600, 40 * 3600)
        else:
            when = elig[p.id] + rng.randrange(2, 30) * 86400
        amount = p.amount if rng.random() < 0.25 else max(
            10000, (p.amount // rng.randint(2, 5)) // 100 * 100)
        add_refund(p, amount, when, "synthesized_documented", doc_ref)

    # --- disputes ----------------------------------------------------------
    disputes: list[dict] = []
    dispute_ref = ("modelled from GET /v1/disputes schema; POST /v1/disputes is HTTP 404 "
                   "(endpoint does not exist) -- see SETTLEMENT_SPEC.md sec 6")
    #: Early fraud/retrieval alerts arrive within days and CAN hold a payment
    #: before it settles. A true chargeback arrives weeks later, long after the
    #: payment has been paid out, and is recovered by a debit adjustment
    #: instead. Modelling both with the same timing would be incoherent.
    EARLY_CODES = [
        ("4855", "Goods or Services Not Provided", "retrieval"),
        ("10.4", "Other Fraud - Card Absent Environment", "fraud"),
    ]
    LATE_CODES = [
        ("4863", "Cardholder Does Not Recognise", "chargeback"),
        ("13.1", "Merchandise/Services Not Received", "chargeback"),
    ]
    patched: dict[str, PaymentEvent] = {}
    for p in payments:
        role = roles[p.id]
        if role not in ("dispute_held", "dispute_won", "dispute_lost"):
            continue
        did = mk("disp")
        if role == "dispute_lost":
            code, desc, phase = rng.choice(LATE_CODES)
            # arrives well after the payment has already settled
            opened = min(p.created_at + rng.randrange(20, 46) * 86400,
                         horizon - 8 * 86400)
            opened = max(opened, p.created_at + 86400)
            status, hold_until, deducted = "lost", None, p.amount
        else:
            code, desc, phase = rng.choice(EARLY_CODES)
            # must land BEFORE T+2 eligibility, or the hold never bites
            opened = rng.randrange(p.created_at + 3600, max(
                elig[p.id] - 1800, p.created_at + 7200))
            if role == "dispute_held":
                status, hold_until, deducted = "under_review", None, 0
            else:
                # the hold must RELEASE with time left to settle, or the
                # "won dispute settles much later" case never occurs at all --
                # and a payment still held at the horizon cannot coherently
                # carry status "won"
                release = min(opened + rng.randrange(21, 40) * 86400,
                              horizon - 17 * 86400)
                if release < opened + 14 * 86400:
                    # not enough runway: this one is still under review
                    status, hold_until, deducted = "under_review", None, 0
                else:
                    status, hold_until, deducted = "won", release, 0
        disputes.append(
            OrderedDict(
                id=did, entity="dispute", payment_id=p.id, amount=p.amount,
                currency="INR", amount_deducted=deducted, reason_code=code,
                reason_description=desc,
                respond_by=opened + 7 * 86400, status=status, phase=phase,
                created_at=opened,
                evidence=OrderedDict(amount=p.amount, summary=None,
                                     shipping_proof=[], billing_proof=None,
                                     submitted_at=None),
                source_tier="synthesized_modelled", source_ref=dispute_ref,
            )
        )
        if role == "dispute_lost":
            adjustments.append(
                AdjustmentEvent(
                    id=mk("adj"),
                    amount=p.amount,
                    created_at=max(opened + 3600, min(
                        opened + rng.randrange(4, 16) * 86400, horizon - 3600)),
                    description=f"Chargeback debit - reason {code}",
                    direction="debit",
                    dispute_id=did,
                    source_tier="synthesized_documented",
                    source_ref="recon sample adj_EhcHONhX4ChgNC shape",
                )
            )
        else:
            patched[p.id] = PaymentEvent(
                **{**p.__dict__, "dispute_id": did, "hold_from": opened,
                   "hold_until": hold_until}
            )

    payments = [patched.get(p.id, p) for p in payments]

    # A debit larger than the settleable credit at its batch: forces the
    # non-negative-payout deferral of SETTLEMENT_SPEC.md sec 1.4 to fire, so
    # the rule is exercised by data rather than merely written down.
    adjustments.append(
        AdjustmentEvent(
            id=mk("adj"),
            amount=rng.randrange(1_200_000, 2_000_000),
            created_at=ts(BATCH_DATES[NEGATIVE_BALANCE_BATCH]) - 3600,
            description="Chargeback recovery - bulk",
            direction="debit",
            source_tier="synthesized_modelled",
            source_ref="standard acquirer practice; no Razorpay source",
        )
    )

    for _ in range(MISC_ADJUSTMENTS):
        kind, direction = rng.choice(
            [("Settlement processing fee", "debit"),
             ("Bank return charge - NEFT rejected", "debit"),
             ("Goodwill credit - service disruption", "credit"),
             ("Fee reversal - overcharged MDR", "credit")]
        )
        adjustments.append(
            AdjustmentEvent(
                id=mk("adj"),
                amount=rng.randrange(500, 40000),
                created_at=ts(WINDOW_START) + rng.randrange(span),
                description=kind,
                direction=direction,
                source_tier="synthesized_modelled",
                source_ref="standard acquirer practice; no Razorpay source",
            )
        )

    return payments, refunds, adjustments, roles, disputes, decoys


# --- ambiguity planting ----------------------------------------------------


def plant_ambiguity(payments, refunds, adjustments, config, rng, mk, targets):
    """Force >=2 tying maximal subsets in the named batches.

    Any sum T achievable by two or more distinct subsets of the eligible pool
    is, by construction, the maximum achievable under a cap of exactly T. So we
    pull `available` down to such a T by inserting one real debit. See
    SETTLEMENT_SPEC.md sec 2.
    """
    planted: list[dict] = []
    for batch_index in targets:
        achieved = False
        for _attempt in range(6):
            result = simulate(payments, refunds, adjustments, config)
            if batch_index >= len(result.batches):
                break
            batch = result.batches[batch_index]
            if batch.ambiguous:
                planted.append({"batch_index": batch_index,
                                "settlement_id": batch.settlement_id,
                                "planted": True})
                achieved = True
                break
            pool = _pool_at(payments, refunds, adjustments, config, batch_index)
            target = _largest_ambiguous_sum(pool, batch.available)
            if target is None or target >= batch.available:
                break
            delta = batch.available - target
            _insert_debit(payments, refunds, adjustments, result, rng, mk,
                          batch.formed_at - 3600, delta,
                          CALIBRATION_REFUND_REF)
        if not achieved:
            # A generator that can silently under-deliver its hardest class is
            # a generator whose output means nothing. Record the miss so the
            # shortfall is a fact in the key, not an absence nobody notices.
            planted.append({"batch_index": batch_index, "settlement_id": None,
                            "planted": False,
                            "reason": "no sum below the live-balance cap is "
                                      "reachable by two or more distinct subsets"})
    return planted


def plant_pressure(payments, refunds, adjustments, config, rng, mk, targets):
    """Force genuine subset-sum EXCLUSIONS in the named batches.

    Pull `available` down to `pool_total - credit(victim)`, which is achievable
    only by dropping value equal to one eligible payment. The dropped payment
    rolls forward to a later batch -- exactly the "partial settlements" case in
    Razorpay's own worked example.
    """
    planted: list[dict] = []
    for batch_index in targets:
        achieved = False
        for _attempt in range(4):
            result = simulate(payments, refunds, adjustments, config)
            if batch_index >= len(result.batches):
                break
            batch = result.batches[batch_index]
            pool = _pool_at(payments, refunds, adjustments, config, batch_index)
            pool_total = sum(v for _n, v in pool)
            if batch.credit_total < pool_total:
                planted.append({"batch_index": batch_index, "planted": True,
                                "settlement_id": batch.settlement_id,
                                "excluded_credit": pool_total - batch.credit_total})
                achieved = True
                break
            if len(pool) < 3:
                break
            counts = Counter(v for _n, v in pool)
            unique = sorted((v for v, c in counts.items() if c == 1))
            if not unique:
                break
            # "drop exactly one" is a linear scan, not subset-sum. On the
            # deep-pressure batches drop a set of three, so the selection
            # genuinely requires combinatorial search.
            if batch_index in DEEP_PRESSURE_BATCHES and len(unique) >= 3:
                dropped = unique[1] + unique[len(unique) // 2] + unique[-2]
            else:
                dropped = unique[len(unique) // 2]
            target = pool_total - dropped
            delta = batch.available - target
            if delta <= 0:
                break
            _insert_debit(payments, refunds, adjustments, result, rng, mk,
                          batch.formed_at - 3600, delta,
                          CALIBRATION_REFUND_REF)
    return planted


#: Debits inserted to shape live balance carry the SAME provenance strings as
#: any other refund or adjustment. A `source_ref` naming the mechanism that
#: created a row would be a stage direction, and `grep ambiguity` would name
#: every provably-unresolvable batch in the dataset.
CALIBRATION_REFUND_REF = ("https://razorpay.com/docs/payments/settlements/ "
                          "(refund reduces live balance)")
CALIBRATION_ADJUSTMENT_REF = "standard acquirer practice; no Razorpay source"


def _insert_debit(payments, refunds, adjustments, result, rng, mk, when, delta, ref):
    """Insert one real debit of exactly `delta` paise, effective before `when`.

    A refund is preferred (more realistic than a fee adjustment), but only
    against a payment with enough UNREFUNDED value left -- otherwise the
    ledger would carry a refund larger than its payment.
    """
    already: dict[str, int] = {}
    for r in refunds:
        already[r.payment_id] = already.get(r.payment_id, 0) + r.amount
    candidates = sorted(
        (p for p in payments
         if result.settled_in.get(p.id)
         and p.amount - already.get(p.id, 0) > delta
         and p.created_at < when),
        key=lambda p: p.id,
    )
    if candidates:
        victim = candidates[rng.randrange(len(candidates))]
        refunds.append(
            RefundEvent(id=mk("rfnd"), payment_id=victim.id, amount=delta,
                        created_at=when,
                        notes=[] if rng.random() < 0.5 else {
                            "reason": rng.choice(REFUND_REASONS)},
                        source_tier="synthesized_documented",
                        source_ref=CALIBRATION_REFUND_REF))
    else:
        adjustments.append(
            AdjustmentEvent(id=mk("adj"), amount=delta, created_at=when,
                            description="Settlement processing fee", direction="debit",
                            source_tier="synthesized_modelled",
                            source_ref=CALIBRATION_ADJUSTMENT_REF))


def _pool_at(payments, refunds, adjustments, config, batch_index):
    """Re-derive the eligible pool the simulator would see at `batch_index`."""
    times = sorted(config.batch_times)
    settled: set[str] = set()
    netted: set[str] = set()
    if batch_index:
        prior = SimulatorConfig(
            batch_times=times[:batch_index],
            settlement_delay_working_days=config.settlement_delay_working_days,
            cutoff_hour=config.cutoff_hour, max_pool=config.max_pool)
        before = simulate(payments, refunds, adjustments, prior)
        settled = set(before.settled_in)
        netted = set(before.netted_out)
    t = times[batch_index]
    elig = {p.id: add_working_days(p.created_at, config.settlement_delay_working_days,
                                   config.cutoff_hour) for p in payments}

    def held(p):
        if p.hold_from is None or t < p.hold_from:
            return False
        return p.hold_until is None or t < p.hold_until

    return sorted(
        ((p.id, p.credit) for p in payments
         if p.captured and p.id not in settled and p.id not in netted
         and not held(p) and elig[p.id] <= t),
        key=lambda kv: kv[0],
    )


#: Achievable-sum DP width. Unbounded, the number of distinct subset sums of a
#: 26-payment pool with arbitrary paise values approaches 2**26, and this
#: function -- which re-sorts the whole table per item -- effectively hangs.
#: Keeping the largest N sums makes it a bounded SEARCH: it may miss a valid
#: target, in which case the plant is recorded as failed rather than silently
#: skipped. Nothing downstream trusts this result -- the simulator verifies
#: ambiguity independently.
MAX_TRACKED_SUMS = 20000


def _largest_ambiguous_sum(pool, cap):
    """Largest sum < cap reachable by >= 2 distinct subsets of `pool`.

    Bounded search, not an exact oracle. See MAX_TRACKED_SUMS.
    """
    if cap <= 0:
        return None
    counts: dict[int, int] = {0: 1}
    for _name, value in sorted(pool, key=lambda kv: (-kv[1], kv[0])):
        for total in sorted(counts, reverse=True):
            if total + value <= cap:
                counts[total + value] = counts.get(total + value, 0) + counts[total]
        if len(counts) > MAX_TRACKED_SUMS:
            # keep the largest sums: the target we want is just below `cap`
            counts = dict(sorted(counts.items(), reverse=True)[:MAX_TRACKED_SUMS])
    for total in sorted(counts, reverse=True):
        if total < cap and counts[total] >= 2:
            return total
    return None


# --- recon row emission ----------------------------------------------------


#: weakest (least defensible) provenance first
TIER_ORDER = ["synthesized_modelled", "synthesized_documented", "captured_real"]


def weakest(*tiers: str) -> str:
    return min(tiers, key=TIER_ORDER.index)


def emit_rows(payments, refunds, adjustments, result, batch_by_id):
    rows = []
    for p in payments:
        sid = result.settled_in.get(p.id)
        batch = batch_by_id.get(sid)
        rows.append(
            OrderedDict(
                entity_id=p.id, type="payment", debit=0,
                credit=p.credit if p.captured else 0,
                amount=p.amount, currency="INR", fee=p.fee, tax=p.tax,
                on_hold=_on_hold_at_horizon(p),
                settled=bool(sid), created_at=p.created_at,
                settled_at=batch.formed_at if batch else None,
                settlement_id=sid, posted_at=None, credit_type="default",
                description=p.description, notes=p.notes,
                payment_id=None,                      # null on `payment` rows
                settlement_utr=batch.utr if batch else None,
                order_id=p.order_id, order_receipt=p.order_receipt,
                method=p.method, card_network=p.card_network,
                card_issuer=p.card_issuer, card_type=p.card_type,
                dispute_id=p.dispute_id,
                source_tier=p.source_tier, source_ref=p.source_ref,
            )
        )
    pay_by_id = {p.id: p for p in payments}
    for r in refunds:
        sid = result.settled_in.get(r.id)
        batch = batch_by_id.get(sid)
        parent = pay_by_id[r.payment_id]
        # provenance can only be weakened by inheritance, never strengthened:
        # a refund against a modelled card payment is itself modelled.
        tier = weakest(r.source_tier, parent.source_tier)
        rows.append(
            OrderedDict(
                entity_id=r.id, type="refund", debit=r.amount, credit=0,
                amount=r.amount, currency="INR", fee=0, tax=0, on_hold=False,
                settled=bool(sid), created_at=r.created_at,
                settled_at=batch.formed_at if batch else None,
                settlement_id=sid, posted_at=None, credit_type="default",
                description=r.description, notes=r.notes,
                payment_id=r.payment_id,              # populated on refund rows
                settlement_utr=batch.utr if batch else None,
                order_id=parent.order_id, order_receipt=parent.order_receipt,
                method=parent.method, card_network=parent.card_network,
                card_issuer=parent.card_issuer, card_type=parent.card_type,
                dispute_id=None,
                source_tier=tier,
                source_ref=r.source_ref,
            )
        )
    for a in adjustments:
        sid = result.settled_in.get(a.id)
        batch = batch_by_id.get(sid)
        debit = a.amount if a.direction == "debit" else 0
        credit = 0 if a.direction == "debit" else a.amount
        rows.append(
            OrderedDict(
                entity_id=a.id, type="adjustment", debit=debit, credit=credit,
                amount=a.amount, currency="INR", fee=0, tax=0, on_hold=False,
                settled=bool(sid), created_at=a.created_at,
                settled_at=batch.formed_at if batch else None,
                settlement_id=sid, posted_at=None,
                # `credit_type` is ABSENT on adjustment rows -- not null.
                description=a.description, notes=[],
                payment_id=None,
                settlement_utr=None,                  # null even with a real sid
                order_id=None, order_receipt=None, method=None,
                card_network=None, card_issuer=None, card_type=None,
                dispute_id=a.dispute_id,
                source_tier=a.source_tier, source_ref=a.source_ref,
            )
        )
    return rows


def _on_hold_at_horizon(p):
    return p.hold_from is not None and p.hold_until is None


# --- companion files -------------------------------------------------------


def build_bank_statement(rng, batches, corrupt_count=3):
    corrupt_at = set(rng.sample(range(len(batches)), corrupt_count))
    # On exactly one corrupted line the JOIN KEY ITSELF is gone, not merely
    # damaged inside free text. A matcher must fall back to (amount, date).
    blanked = sorted(corrupt_at)[len(corrupt_at) // 2]
    out = []
    for i, b in enumerate(batches):
        narration = (
            f"NEFT-CR-RATN0000088-RAZORPAY SOFTWARE PVT LTD-"
            f"ACME RETAIL PRIVATE LIMITED-{b.utr}"
        )
        if i in corrupt_at:
            style = rng.randrange(3)
            if style == 0:
                narration = narration[: rng.randint(38, 52)]
            elif style == 1:
                narration = narration.replace(b.utr, b.utr[:6] + "*" * 6)
            else:
                narration = "NEFT-CR-RATN0000088-RAZORPAY  SOFTWA"
        out.append(
            OrderedDict(
                utr="" if i == blanked else b.utr,
                date=iso_date(b.formed_at),
                narration=narration, amount=rupees(b.payout),
            )
        )
    return out, sorted(corrupt_at), blanked


def build_erp_and_gst(rng, payments, batches, rows):
    merchant_gstin = make_gstin(rng, MERCHANT_GSTIN_STATE)
    razorpay_gstin = make_gstin(rng, MERCHANT_GSTIN_STATE)
    rounding_residuals: list[OrderedDict] = []

    erp = []
    captured_payments = sorted([p for p in payments if p.captured], key=lambda p: p.id)
    # An unsettled payment reasonably has no invoice yet, so sampling those
    # would not test the invariant we care about: money received, no ERP order.
    settled_ids = sorted({r["entity_id"] for r in rows
                          if r["type"] == "payment" and r["settlement_id"]})
    missing_in_erp = set(rng.sample(settled_ids, max(1, len(settled_ids) // 12)))
    seq = 1000
    for p in sorted(captured_payments, key=lambda p: (p.created_at, p.id)):
        if p.id in missing_in_erp:
            continue
        seq += 1
        inv = f"ACM/26-27/{seq}"
        erp.append(
            OrderedDict(
                order_id=p.order_id, invoice_no=inv,
                # most retail orders are B2C: the customer has no GSTIN and the
                # document is a bill of supply, not a B2B tax invoice
                gstin=make_gstin(rng) if rng.random() < 0.15 else "",
                amount=rupees(p.amount), invoice_date=iso_date(p.created_at),
            )
        )
    orphans = []
    span = int((WINDOW_END - WINDOW_START).total_seconds())
    for _ in range(6):
        seq += 1
        inv = f"ACM/26-27/{seq}"
        when = ts(WINDOW_START) + rng.randrange(span)
        orphans.append(inv)
        erp.append(
            OrderedDict(
                order_id=f"order_{''.join(rng.choice(B62) for _ in range(14))}",
                invoice_no=inv,
                gstin=make_gstin(rng) if rng.random() < 0.15 else "",
                amount=rupees(rng.randrange(50000, 900000)),
                invoice_date=iso_date(when),
            )
        )
    erp.sort(key=lambda r: (r["invoice_date"], r["invoice_no"]))

    # --- GSTR-2B: the merchant's INWARD-supply ITC statement ---------------
    # Razorpay deducts its fee per settlement but issues ONE CONSOLIDATED TAX
    # INVOICE PER MONTH (dashboard "Monthly Invoice"; RazorpayX billing doc
    # states it is generated on the 1st of the following month). So a single
    # 2B line must tie back to N settlements' fee columns -- which is both more
    # realistic and a harder reconciliation than one line per batch.
    fee_by_month: dict[str, list[int]] = {}
    for row in rows:
        sid = row["settlement_id"]
        if not sid or row["type"] != "payment" or not row["fee"]:
            continue
        month = iso_date(row["settled_at"])[:7]
        acc = fee_by_month.setdefault(month, [0, 0, 0])
        if row["tax"]:
            acc[0] += row["fee"] - row["tax"]
            acc[1] += row["tax"]
        else:
            # fee charged with no GST component -> nothing to claim ITC on,
            # and it must not inflate the invoice's taxable value
            acc[2] += row["fee"]

    months = sorted(fee_by_month)
    missing_from_2b = {months[1]} if len(months) > 1 else set()
    no_irn = {months[-1]} if len(months) > 2 else set()

    gstr2b, itc_at_risk = [], []
    for index, month in enumerate(months):
        accrued_excl, accrued_tax, fee_without_gst = fee_by_month[month]
        # A real consolidated invoice computes GST ONCE on the aggregate
        # taxable value. Summing per-transaction ceiling-rounded tax does not
        # give the same number -- the difference is a genuine reconciliation
        # residual, and it is recorded rather than papered over.
        cgst = ceil_div(accrued_excl * 9, 100)
        sgst = cgst
        invoiced_tax = cgst + sgst
        year, mon = (int(part) for part in month.split("-"))
        invoice_date = (datetime(year, mon, 1, tzinfo=IST)
                        + timedelta(days=32)).replace(day=1)
        inv_no = f"RZP/BLR/26-27/{7000 + index}"

        if month in missing_from_2b:
            # Supplier never furnished it in GSTR-1, so it never reached 2B.
            # No ITC under Sec 16(2)(aa) CGST -- the recipient has no record
            # to accept in IMS, so nothing populates 2B.
            itc_at_risk.append(OrderedDict(
                invoice_no=inv_no, period=month, reason="absent_from_gstr2b",
                statute="Sec 16(2)(aa) CGST", itc_paise=invoiced_tax))
            continue

        if month in no_irn:
            # Razorpay's AATO is far above the e-invoicing threshold, so its
            # invoice MUST carry an IRN. One without is not a tax invoice at
            # all under Rule 48(5), and ITC fails for want of a valid document.
            #
            # NOTE: the naive "IRN generated >30 days late" scenario is
            # MECHANICALLY IMPOSSIBLE and is deliberately NOT modelled -- the
            # IRP refuses to register the document past the window, so no IRN
            # exists and the line never auto-populates into 2B. A row that is
            # both in 2B and late-IRN cannot occur.
            irn, irn_at = "", ""
            itc_at_risk.append(OrderedDict(
                invoice_no=inv_no, period=month,
                reason="no_irn_on_notified_supplier_invoice",
                statute="Rule 48(5) CGST", itc_paise=invoiced_tax))
            availability, filed_period, filed = "No", f"{month}", "Y"
        else:
            irn = "".join(rng.choice("0123456789abcdef") for _ in range(64))
            irn_at = (invoice_date + timedelta(days=rng.randrange(0, 3))
                      ).strftime("%Y-%m-%d")
            availability, filed_period, filed = "Yes", f"{month}", "Y"

        # Rule 37A: ITC validly taken must be REVERSED (with interest at 18%
        # p.a.) if the supplier has not filed GSTR-3B by 30 September of the
        # following financial year. GSTR-2B does NOT flag this for you -- it is
        # a condition a recon engine genuinely has to compute, which is why it
        # is the most interesting ITC exposure to plant.
        if index == 0:
            filed = "N"
            availability = "Yes"          # 2B still shows it as available
            itc_at_risk.append(OrderedDict(
                invoice_no=inv_no, period=month,
                reason="supplier_gstr3b_not_filed_rule_37a",
                statute="Rule 37A CGST", itc_paise=invoiced_tax))

        gstr2b.append(
            OrderedDict(
                gstin=razorpay_gstin, invoice_no=inv_no,
                invoice_date=invoice_date.strftime("%Y-%m-%d"),
                taxable_value=rupees(accrued_excl), igst=rupees(0),
                cgst=rupees(cgst), sgst=rupees(sgst),
                irn=irn, irn_generated_at=irn_at,
                gstr1_filing_period=filed_period,
                supplier_gstr3b_filed=filed,
                itc_availability=availability,
            )
        )
        if invoiced_tax != accrued_tax:
            rounding_residuals.append(OrderedDict(
                invoice_no=inv_no, period=month,
                accrued_tax_paise=accrued_tax,
                invoiced_tax_paise=invoiced_tax,
                residual_paise=invoiced_tax - accrued_tax,
                fee_charged_without_gst_paise=fee_without_gst))

    # unrelated vendor inward supplies, for realism
    for _ in range(18):
        vendor_state = f"{rng.randint(1, 37):02d}"
        interstate = vendor_state != MERCHANT_GSTIN_STATE
        taxable = rng.randrange(200000, 4000000)
        when = ts(WINDOW_START) + rng.randrange(span)
        half = ceil_div(taxable * 9, 100)
        igst = ceil_div(taxable * 18, 100)
        gstr2b.append(
            OrderedDict(
                gstin=make_gstin(rng, vendor_state),
                invoice_no=f"{rng.choice(VENDOR_NAMES)[:3]}/{rng.randrange(100, 999)}",
                invoice_date=iso_date(when),
                taxable_value=rupees(taxable),
                igst=rupees(igst if interstate else 0),
                cgst=rupees(0 if interstate else half),
                sgst=rupees(0 if interstate else half),
                irn="".join(rng.choice("0123456789abcdef") for _ in range(64)),
                irn_generated_at=iso_date(when + rng.randrange(0, 3) * 86400),
                gstr1_filing_period=iso_date(when)[:7],
                supplier_gstr3b_filed="Y",
                itc_availability="Yes",
            )
        )
    gstr2b.sort(key=lambda r: (r["invoice_date"], r["invoice_no"]))
    return (erp, gstr2b, merchant_gstin, razorpay_gstin, sorted(missing_in_erp),
            orphans, itc_at_risk, rounding_residuals)


# --- class labelling (derived from what actually happened) -----------------


def classify(rows, payments, refunds, result, batches, corrupt_at, decoys):
    by_entity = {r["entity_id"]: r for r in rows}
    batch_by_id = {b.settlement_id: b for b in batches}
    order = {b.settlement_id: i
             for i, b in enumerate(sorted(batches, key=lambda b: b.formed_at))}
    labels: dict[str, set[str]] = {r["entity_id"]: set() for r in rows}
    elig = {p.id: add_working_days(p.created_at, 2, 17) for p in payments}
    refunds_for: dict[str, list] = {}
    for r in refunds:
        refunds_for.setdefault(r.payment_id, []).append(r)

    for p in payments:
        row = by_entity[p.id]
        sid = row["settlement_id"]
        rs = refunds_for.get(p.id, [])
        total_refunded = sum(r.amount for r in rs)
        if sid and not rs and not p.dispute_id:
            labels[p.id].add("c01_clean_1to1")
        if rs and total_refunded == p.amount and all(r.created_at <= elig[p.id] for r in rs):
            labels[p.id].add("c02_full_refund_pre_settlement")
            for r in rs:
                labels[r.id].add("c02_full_refund_pre_settlement")
        if rs and total_refunded < p.amount and any(r.created_at <= elig[p.id] for r in rs):
            labels[p.id].add("c03_partial_refund_pre_settlement")
            for r in rs:
                if r.created_at <= elig[p.id]:
                    labels[r.id].add("c03_partial_refund_pre_settlement")
        for r in rs:
            rsid = by_entity[r.id]["settlement_id"]
            if sid and rsid and order.get(rsid, -1) > order.get(sid, -1):
                labels[r.id].add("c04_refund_in_later_batch")
        if sid:
            first_possible = min((b for b in batches if b.formed_at >= elig[p.id]),
                                 key=lambda b: b.formed_at, default=None)
            if (first_possible and order[sid] > order[first_possible.settlement_id]
                    and not p.dispute_id):
                labels[p.id].add("c05_subset_sum_rolled_forward")
            if (datetime.fromtimestamp(p.created_at, IST).month
                    != datetime.fromtimestamp(batch_by_id[sid].formed_at, IST).month):
                labels[p.id].add("c11_cross_month_boundary")
        if p.dispute_id and not sid and row["on_hold"]:
            labels[p.id].add("c08_dispute_hold")
        if p.dispute_id and sid and p.hold_from is not None and p.hold_until is not None:
            labels[p.id].add("c10_won_dispute_settles_later")

    for row in rows:
        if row["type"] == "adjustment":
            if row["dispute_id"]:
                labels[row["entity_id"]].add("c09_lost_dispute_adjustment")
            if row["settlement_id"] and row["settlement_utr"] is None:
                labels[row["entity_id"]].add("c12_shared_sid_null_utr")
        if row["notes"] == [] or "credit_type" not in row:
            labels[row["entity_id"]].add("c13_schema_variance")

    for source_id, target_id in decoys:
        for entity_id in (source_id, target_id):
            labels[entity_id].add("c15_same_day_same_amount_decoy")

    batch_labels: dict[str, set[str]] = {b.settlement_id: set() for b in batches}
    for b in batches:
        if b.ambiguous:
            batch_labels[b.settlement_id].add("c07_ambiguous_decomposition")
        if len(b.credit_ids) > 1 and len(b.debit_ids) >= 1:
            batch_labels[b.settlement_id].add("c06_netting")
    for i, b in enumerate(sorted(batches, key=lambda b: b.formed_at)):
        if i in corrupt_at:
            batch_labels[b.settlement_id].add("c14_corrupt_bank_narration")
    return labels, batch_labels


# --- writers ---------------------------------------------------------------


def _resolve_ids(entries, result):
    """Planting runs against throwaway simulations whose settlement ids are
    placeholders. Re-key every planting record onto the FINAL ids, or an eval
    harness joining on them silently matches nothing."""
    final = sorted(result.batches, key=lambda b: b.formed_at)
    out = []
    for entry in entries:
        index = entry["batch_index"]
        resolved = dict(entry)
        resolved["settlement_id"] = (
            final[index].settlement_id if index < len(final) else None)
        out.append(OrderedDict(sorted(resolved.items())))
    return out


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[OrderedDict]) -> None:
    with path.open("w", newline="\n") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate(seed: int, out: Path, truth: Path):
    rng = random.Random(seed)
    mk = make_id_factory(rng)
    config = SimulatorConfig(batch_times=[ts(d) for d in BATCH_DATES])

    payments, refunds, adjustments, roles, disputes, decoys = build_ledger(rng, mk)
    pressured = plant_pressure(payments, refunds, adjustments, config, rng, mk,
                               PRESSURE_BATCHES)
    planted = plant_ambiguity(payments, refunds, adjustments, config, rng, mk,
                              AMBIGUITY_BATCHES)
    result = simulate(payments, refunds, adjustments, config, id_maker=mk)
    batch_by_id = {b.settlement_id: b for b in result.batches}

    rows = emit_rows(payments, refunds, adjustments, result, batch_by_id)
    rows.sort(key=lambda r: (r["created_at"], r["entity_id"]))

    bank, corrupt_at, blanked_utr_index = build_bank_statement(
        rng, sorted(result.batches, key=lambda b: b.formed_at))
    (erp, gstr2b, m_gstin, rz_gstin, missing_erp, orphans, itc_risk,
     gst_residuals) = build_erp_and_gst(
        rng, payments, result.batches, rows)
    labels, batch_labels = classify(rows, payments, refunds, result,
                                    result.batches, corrupt_at, decoys)

    out.mkdir(parents=True, exist_ok=True)
    truth.mkdir(parents=True, exist_ok=True)

    write_json(out / "recon_combined.json",
               OrderedDict(entity="collection", count=len(rows), items=rows))
    write_json(out / "disputes.json", OrderedDict(
        entity="collection", count=len(disputes),
        items=sorted(disputes, key=lambda d: (d["created_at"], d["id"]))))
    write_csv(out / "bank_statement.csv", bank)
    write_csv(out / "erp_orders.csv", erp)
    write_csv(out / "gstr2b.csv", gstr2b)

    write_json(truth / "ground_truth.json", OrderedDict(
        seed=seed,
        generated_by="engine/generator.py",
        spec="engine/SETTLEMENT_SPEC.md",
        selection_rule=config.selection_rule,
        warning="ISOLATED. No solver module may read this file.",
        merchant_gstin=m_gstin, razorpay_gstin=rz_gstin,
        settled_in=OrderedDict(sorted(result.settled_in.items())),
        unsettled_reason=OrderedDict(sorted(result.unsettled_reason.items())),
        netted_out=sorted(result.netted_out),
        batches=[OrderedDict(
            settlement_id=b.settlement_id, utr=b.utr, formed_at=b.formed_at,
            formed_on=iso_date(b.formed_at), available_live_balance=b.available,
            credit_ids=list(b.credit_ids), debit_ids=list(b.debit_ids),
            selected_payment_credit=b.selected_credit, credit_total=b.credit_total, debit_total=b.debit_total,
            bank_payout=b.payout, ambiguous=b.ambiguous,
            tying_decompositions=[list(w) for w in b.tying_decompositions],
            tying_decompositions_truncated=b.tying_decompositions_truncated,
            selection_degraded=b.selection_degraded, pool_size=b.pool_size,
            classes=sorted(batch_labels[b.settlement_id]),
        ) for b in sorted(result.batches, key=lambda b: b.formed_at)],
        row_classes=OrderedDict((k, sorted(v)) for k, v in sorted(labels.items()) if v),
        planted_ambiguity=_resolve_ids(planted, result),
        planted_balance_pressure=_resolve_ids(pressured, result),
        payments_missing_from_erp=missing_erp,
        erp_orphan_invoices=orphans,
        itc_at_risk=itc_risk,
        gst_rounding_residuals=gst_residuals,
        corrupt_bank_narration_batch_index=corrupt_at,
        blanked_utr_bank_row_index=blanked_utr_index,
        decoy_pairs=[list(pair) for pair in decoys],
    ))

    write_hashes(out, truth)

    counts: Counter = Counter()
    for values in labels.values():
        counts.update(values)
    for values in batch_labels.values():
        counts.update(values)
    return rows, result, labels, batch_labels, counts


#: files whose SHA-256 is frozen. The ground-truth key is hashed too, so that
#: tampering with the answers after the freeze commit is detectable.
FROZEN = ["recon_combined.json", "disputes.json", "bank_statement.csv",
          "erp_orders.csv", "gstr2b.csv"]


def write_hashes(out: Path, truth: Path) -> None:
    repo = ROOT.parent
    lines = [
        "# SHA-256 of every frozen data file, written by engine/generator.py.",
        "#",
        "# This is TAMPER DETECTION, not proof of authorship order: it shows the",
        "# committed data is exactly what the committed generator produces. A file",
        "# cannot attest to what did not yet exist beside it. See ROBUSTNESS.md",
        "# for the multi-seed evidence that the data was not tuned to a solver.",
        "# Verify:  shasum -a 256 -c <(sed 's|^\\([0-9a-f]*\\) |\\1  |' DATASET_HASHES.txt)",
        "",
    ]
    targets = [out / name for name in FROZEN] + [truth / "ground_truth.json"]
    for path in targets:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            rel = path.resolve().relative_to(repo)
        except ValueError:
            rel = path.resolve()
        lines.append(f"{digest} {rel}")
    (out.parent / "DATASET_HASHES.txt").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260822)
    ap.add_argument("--out", default=str(ROOT / "data"))
    ap.add_argument("--truth", default=str(ROOT / "ground_truth"))
    args = ap.parse_args()
    rows, result, _labels, _bl, counts = generate(
        args.seed, Path(args.out), Path(args.truth))
    tiers = Counter(r["source_tier"] for r in rows)
    print(f"rows={len(rows)} batches={len(result.batches)}")
    print("classes:", json.dumps(dict(sorted(counts.items())), indent=1))
    print("tiers:", dict(tiers))
    print("ambiguous:", [b.settlement_id for b in result.batches if b.ambiguous])


if __name__ == "__main__":
    main()
