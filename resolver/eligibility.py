"""Which ledger rows could have been in a given bank credit.

Every rule here is a rule the MERCHANT can apply from `SETTLEMENT_SPEC.md` and
its own recon file. Nothing in this module reads a settlement identifier, and
nothing in it reads ground truth.

The pool is the resolver's model of the world, and getting it wrong is not a
neutral error: a pool that is too small makes the true composition
unreachable, and a pool that is too large makes closure non-unique and drives
the resolver into `Ambiguous`. The first failure is silent and the second is
loud, so where the rules are uncertain this module errs LARGE.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

#: `SETTLEMENT_SPEC.md` 1.2: T+2 working days, cutoff 11:00 IST. Merchant-
#: visible published product behaviour, not a fact about the answer key.
SETTLEMENT_DELAY_WORKING_DAYS = 2
CUTOFF_HOUR = 11


def eligible_at(created_at: int) -> int:
    """The first instant a payment created at `created_at` may settle."""
    moment = datetime.fromtimestamp(created_at, IST)
    remaining = SETTLEMENT_DELAY_WORKING_DAYS
    while remaining > 0:
        moment += timedelta(days=1)
        if moment.weekday() < 5:
            remaining -= 1
    return int(moment.replace(hour=CUTOFF_HOUR, minute=0, second=0,
                              microsecond=0).timestamp())


def end_of_day(day: date) -> int:
    return int(datetime.combine(day, datetime.min.time(),
                                tzinfo=IST).timestamp()) + 86_400


def net(row: dict) -> int:
    """Signed contribution in integer paise. Credits positive, debits negative.

    Money is integer paise everywhere in this repository and no float
    arithmetic touches it.
    """
    return row["credit"] - row["debit"]


def pool_at(rows: list[dict], value_date: date, consumed: set[str]
            ) -> list[tuple[str, int]]:
    """Rows that could have composed a credit posted on `value_date`.

    Excluded, each for a reason the merchant can state:

    * already consumed by a `Verified` outcome -- a row settles once;
    * `on_hold` -- disputed funds are locked and do not settle;
    * an uncaptured payment -- it never became money;
    * created after the bank posted -- it did not exist when the money left;
    * a payment not yet eligible under T+2 at the posting date.

    The value DATE rather than the settlement instant is the ceiling, because
    the settlement instant is exactly what the resolver does not know. That
    makes the pool a superset of the true one, which is the safe direction.
    """
    ceiling = end_of_day(value_date)
    out: list[tuple[str, int]] = []
    for row in rows:
        if row["entity_id"] in consumed:
            continue
        if row.get("on_hold"):
            continue
        if row["created_at"] > ceiling:
            continue
        if row["type"] == "payment":
            if row["credit"] == 0:
                continue                       # never captured
            if eligible_at(row["created_at"]) > ceiling:
                continue
        if net(row) == 0:
            continue                           # contributes nothing either way
        out.append((row["entity_id"], net(row)))
    return out
