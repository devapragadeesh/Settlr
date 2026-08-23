"""The bank statement, as a genuinely independent source. Defect D4's fix.

## The defect, measured

In the frozen dataset:

    settlement_utr == str(settled_at) + settlement_id[-6:]      11 of 11 batches
    narration contains its own utr verbatim                      9 of 12 lines
    bank posting date - settled_at date                          0 days, always
    distinct bank dates / bank lines                             12 / 12
    bank lines / batches                                         12 / 12, in order

So the "bank statement" is a re-encoding of the settlement record. "12/12
matched on UTR" measures the generator. And even with the UTR deleted the join
survives: unique dates at zero lag mean **date-sorting alone recovers the exact
true settlement sequence**, and a same-day collision is structurally
impossible.

## The fix is structural, not cosmetic

The guarantee is a function signature: **the bank statement is produced by a
function that is never passed a settlement identifier.** `Payout` carries an
amount and an initiation timestamp and nothing else -- no settlement id, no
entity ids, no batch object. Compare `engine/generator.build_bank_statement`,
which receives `Batch` objects and writes `b.utr` into both the `utr` column
and the narration.

The tests in `corpus/tests/test_bank_independence.py` corroborate the
guarantee; the signature is the guarantee.

## Where the line is between legitimate signal and a leak

> A bank field may CORRELATE with a ledger field through a modelled physical
> mechanism. A bank field may not be COMPUTED FROM a ledger field.

Permitted, enumerated, and named in `corpus/CORPUS_SPEC.md` §5:

1. **amount** -- the credit is the credit. This *must* leak; it is the join
   evidence and the reason reconciliation is possible at all.
2. **posting date within a few days of settlement** -- money really does land
   near the settlement date. Modelled, recorded, and no longer a constant.
3. **counterparty text naming Razorpay** -- it really is the remitter.

`utr = f"{t}{settlement_id[-6:]}"` is on the wrong side of that line: it is a
pure function of ledger state.

## Honesty boundary, stated rather than glossed

You cannot test "no function from bank line to ledger field exists." You can
test that an enumerated family of functions does not exist, and you can make
the structural argument that the generator never receives the input. That
pairing is the defensible position; claiming the universal negative is not.
"""

from __future__ import annotations

import random
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Sequence

from engine.simulator import IST

__all__ = ["Payout", "BankLineTruth", "BankFile", "build_bank_statement",
           "BANK_IFSC", "rupees"]

#: The merchant's own bank. A real IFSC prefix shape; the branch code is the
#: merchant's, not Razorpay's, because it is the merchant's statement.
BANK_IFSC = "RATN0000088"
BANK_PREFIX = "RATN"


def rupees(paise: int) -> str:
    """Integer paise -> a rupee string, by divmod. Never float division."""
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}{whole}.{frac:02d}"


@dataclass(frozen=True, slots=True)
class Payout:
    """Everything the bank is allowed to know about a settlement.

    No settlement id. No entity ids. No `Batch`. If a field is not on this
    dataclass, no bank-side artefact can possibly encode it -- which is the
    entire point, and is why the type is this small.
    """

    amount_paise: int
    initiated_at: int


@dataclass(frozen=True, slots=True)
class BankLineTruth:
    """What the GENERATOR knows about a bank line. Never written to the
    solver-visible file; goes to the ground-truth key.

    `payout_index` is a position in the `payouts` sequence the caller passed
    in, so the caller can map it back to a settlement id. The bank module
    itself never sees one.
    """

    line_index: int
    payout_index: int | None      # None => a foreign line, not ours
    kind: str                     # settlement | foreign_credit | foreign_debit
    #                             # | reversal_debit
    posting_lag_days: int | None
    reference_visible: bool


@dataclass
class BankFile:
    rows: list[OrderedDict]
    truth: list[BankLineTruth]
    #: Diagnostics for the generation report, not for the solver.
    reference_gaps: list[int] = field(default_factory=list)
    lag_histogram: dict[int, int] = field(default_factory=dict)


# --------------------------------------------------------------------------
# narration -- bank-side formatting only
# --------------------------------------------------------------------------

#: Remitter-name variants. A real statement is not consistent about this, and
#: the variation gives a fuzzy-narration stage legitimate work to do that is
#: not a hidden identifier.
REMITTERS = [
    "RAZORPAY SOFTWARE PVT LTD",
    "RAZORPAY SOFTWARE PRIVATE LIMITED",
    "RAZORPAYSOFTWAREP",
    "RAZORPAY SOFTWARE",
]

FOREIGN_REMITTERS = [
    "NIMBUS LOGISTICS LLP", "VERTEX SUPPLY CO", "TOLLGATE MEDIA PVT LTD",
    "ARCLIGHT SYSTEMS", "SIXFOLD TRADING", "CLOVERLEAF FOODS PVT LTD",
]

#: Narration templates. `{ref}` is the BANK's reference; no ledger field is
#: available to interpolate, because none was passed in.
CREDIT_TEMPLATES = [
    "NEFT-CR-{ifsc}-{remitter}-{me}-{ref}",
    "NEFT CR {ref} {remitter}",
    "RTGS-CR-{ref}-{remitter}",
    "IMPS/{ref}/{remitter}",
    "NEFT-CR-{ifsc}-{remitter}",          # reference NOT in the narration
]

DEBIT_TEMPLATES = [
    "NEFT-DR-{ifsc}-{beneficiary}-{ref}",
    "CHG:NEFT OUTWARD {ref}",
    "NEFT RET {ref} - ACCOUNT CLOSED",
]

MERCHANT = "ACME RETAIL PRIVATE LIMITED"


def _roll_forward(day: date, holidays: frozenset[date]) -> int:
    """Banks do not post on Sunday. Returns extra days added."""
    added = 0
    while day.weekday() >= 5 or day in holidays:
        day += timedelta(days=1)
        added += 1
    return added


def build_bank_statement(
    payouts: Sequence[Payout],
    rng: random.Random,
    *,
    holidays: frozenset[date] = frozenset(),
    foreign_credits: int = 0,
    foreign_debits: int = 0,
    reversals: Sequence[int] = (),
    corrupt_narrations: int = 0,
    blank_references: int = 0,
    lag_weights: Sequence[tuple[int, int]] = ((0, 45), (1, 35), (2, 15), (3, 5)),
) -> BankFile:
    """Build a bank statement that shares nothing with the ledger but money.

    `reversals` names positions in `payouts` whose credit the bank later
    reverses with a debit -- the shape `SETTLEMENT_SPEC.md` §10 named as the
    most common real recon exception and deferred.

    ## The reference

    A bank-side counter with its own sequence and its own gaps:

        RATN<yy><jjj><seq:06d>       e.g. RATN26189004417

    `seq` advances by a random 1..40 between *our* lines, because the branch
    clears other customers' NEFT too. **The gaps are the evidence the counter
    is not ours.** A dense gapless sequence would be a counter minted for this
    file, which is a leak of a different shape.

    ## The posting date

    `initiated_at` + a lag drawn from `lag_weights`, then rolled forward off
    weekends and holidays. About half the lines therefore do NOT share a date
    with their settlement, which is what removes the free exact-date join and
    makes same-date collisions possible for the first time.

    ## The ordering

    `(posting_date, reference)` -- the BANK's order. Once lags differ this is
    not settlement order, and the interleaved foreign lines break the
    line-count bijection as well.
    """
    lags = [lag for lag, _weight in lag_weights]
    weights = [weight for _lag, weight in lag_weights]

    # --- bank-side counter, seeded independently of anything ledger-side ----
    sequence = rng.randrange(100_000, 900_000)
    gaps: list[int] = []

    def next_reference(when: date) -> str:
        nonlocal sequence
        gap = rng.randint(1, 40)
        gaps.append(gap)
        sequence += gap
        return (f"{BANK_PREFIX}{when.strftime('%y')}"
                f"{when.timetuple().tm_yday:03d}{sequence % 1_000_000:06d}")

    @dataclass
    class Pending:
        posted: date
        amount: int
        kind: str
        payout_index: int | None
        lag: int | None

    pending: list[Pending] = []
    for index, payout in enumerate(payouts):
        started = datetime.fromtimestamp(payout.initiated_at, IST).date()
        lag = rng.choices(lags, weights=weights, k=1)[0]
        posted = started + timedelta(days=lag)
        lag += _roll_forward(posted, holidays)
        posted = started + timedelta(days=lag)
        pending.append(Pending(posted, payout.amount_paise, "settlement",
                               index, lag))

    # --- reversals: a bank DEBIT undoing an earlier credit ------------------
    for index in reversals:
        origin = pending[index]
        after = rng.randint(1, 4)
        posted = origin.posted + timedelta(days=after)
        after += _roll_forward(posted, holidays)
        pending.append(Pending(origin.posted + timedelta(days=after),
                               -origin.amount, "reversal_debit", index, None))

    # --- foreign lines: this is a bank account, not a settlement feed -------
    if pending:
        span_start = min(p.posted for p in pending)
        span_days = max((max(p.posted for p in pending) - span_start).days, 1)
    else:                                       # pragma: no cover - defensive
        span_start, span_days = date(2026, 6, 1), 1
    for _ in range(foreign_credits):
        posted = span_start + timedelta(days=rng.randrange(span_days + 1))
        posted += timedelta(days=_roll_forward(posted, holidays))
        pending.append(Pending(posted, rng.randrange(50_000, 4_000_000),
                               "foreign_credit", None, None))
    for _ in range(foreign_debits):
        posted = span_start + timedelta(days=rng.randrange(span_days + 1))
        posted += timedelta(days=_roll_forward(posted, holidays))
        pending.append(Pending(posted, -rng.randrange(20_000, 900_000),
                               "foreign_debit", None, None))

    # --- emit in the BANK's order ------------------------------------------
    pending.sort(key=lambda p: (p.posted, p.kind, p.amount,
                                p.payout_index if p.payout_index is not None else -1))

    references = [next_reference(item.posted) for item in pending]
    hidden = set(rng.sample(range(len(pending)), min(corrupt_narrations, len(pending))))
    blanked = set(rng.sample(sorted(hidden), min(blank_references, len(hidden)))) \
        if hidden else set()

    rows: list[OrderedDict] = []
    truth: list[BankLineTruth] = []
    lag_histogram: dict[int, int] = {}
    for position, (item, reference) in enumerate(zip(pending, references)):
        is_credit = item.amount >= 0
        if is_credit and item.kind == "settlement":
            remitter = rng.choice(REMITTERS)
        elif is_credit:
            remitter = rng.choice(FOREIGN_REMITTERS)
        else:
            remitter = rng.choice(FOREIGN_REMITTERS + REMITTERS)

        template = rng.choice(CREDIT_TEMPLATES if is_credit else DEBIT_TEMPLATES)
        narration = template.format(ifsc=BANK_IFSC, remitter=remitter,
                                    me=MERCHANT, ref=reference,
                                    beneficiary=remitter)
        if position in hidden:
            # bank-side damage: truncation and masking. The reference is
            # removed, never replaced by something derivable.
            style = rng.randrange(3)
            if style == 0:
                narration = narration[:rng.randint(24, 40)]
            elif style == 1:
                narration = narration.replace(reference, reference[:4] + "*" * 8)
            else:
                narration = f"NEFT-CR-{BANK_IFSC}-CLG"
        visible = position not in blanked
        rows.append(OrderedDict(
            bank_reference="" if not visible else reference,
            value_date=item.posted.isoformat(),
            narration=narration,
            amount=rupees(item.amount),
        ))
        truth.append(BankLineTruth(
            line_index=position, payout_index=item.payout_index,
            kind=item.kind, posting_lag_days=item.lag,
            reference_visible=visible))
        if item.lag is not None:
            lag_histogram[item.lag] = lag_histogram.get(item.lag, 0) + 1

    return BankFile(rows=rows, truth=truth, reference_gaps=gaps,
                    lag_histogram=dict(sorted(lag_histogram.items())))
