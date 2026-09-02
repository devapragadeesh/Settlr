"""The wrong-*bank*-side class: a bank credit posted at the wrong amount.

## Why this module exists, and why it is not in `bank.py`

Every planted record error in this corpus so far corrupts the PSP's
attestation -- `d03_wrong_attestation`, `d11_false_settlement_id`. The
benchmark never once tests the direction where the BANK side disagrees and
is the one that is wrong: a bank-side deduction, a teller miskey, a rounding
error introduced by the bank's own posting process. `AttestationDiscrepancy`'s
own contract text is symmetric -- "the sources disagree ... a finding about
the record, not a claim about which rows settled" -- and this module is what
exercises the untested half of that symmetry. See `DECISIONS.md` 51.

`bank.py` is not edited. This module is called from `build.py` on the
`payouts` sequence *before* `build_bank_statement` runs, so the independence
guarantee `bank.py` encodes in `Payout`'s signature -- amount and timestamp,
nothing else -- is exercised by this class, not weakened by it. This module
imports only `Payout` from `bank.py`; it constructs no bank artefact itself.

## The shape: a bank-side deduction or miskey, not a forgery

A real bank statement occasionally posts a NEFT credit short (a deducted
charge folded in the wrong direction) or fat-fingers a digit at the teller.
Framed that way -- not as an adversary rewriting a ledger -- the corruption
is: take one `Payout`'s `amount_paise` and replace it with an amount drawn
from a delta unrelated to any ledger row, so that when `build_bank_statement`
later turns `payouts` into `bank_statement.csv`, that one line's `amount`
column no longer matches the true settlement payout. `recon_combined.json`
and `settlement_report.csv` are built from the batch objects directly and are
never touched by this module, so the PSP's own artefacts stay correct -- the
disagreement is real, and it is the bank that is wrong.

## What this function is not allowed to see

`plant_mispost` receives exactly what `Payout` carries: `amount_paise` and
`initiated_at`. It has no access to a settlement id, a batch object, or any
other ledger-derived value, so the corrupted line cannot be handed back a
settlement id, a UTR, or anything else that would let a resolver identify it
by a channel other than the amount contradiction itself.

## The honesty discipline, mirroring `plant_false_composition`

No row is minted. The function only perturbs an amount that already exists
on an already-simulated `Payout`. And it can decline: if a candidate
corrupted amount would collide with another payout's true amount -- which
would make the corrupted line look like a legitimate, unrelated settlement
rather than a contradiction -- or if it would flip non-positive, the function
returns `None` in place of a truth record rather than forcing a delta that
happens to "work." The caller then ships the dataset without the plant for
that index, exactly as `plant_false_composition` ships `datasets_v2/A20_B0_Cmax`
without its plant.

## What "nearby" means here, honestly

This module has no access to any ledger row or batch composition -- by
design, per `Payout`'s signature -- so it cannot check the corrupted amount
against the full universe of subset sums a solver might reconstruct. What it
CAN check, and does, is that the corrupted amount does not collide with any
OTHER payout's true amount in this same file, which is the one comparison
available at this layer without importing ledger state. That is a narrower
guarantee than "matches no valid batch composition anywhere," and is stated
as a limitation rather than implied to be more than it is.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from corpus.generator.bank import Payout

__all__ = ["MispostTruth", "plant_mispost"]

#: The corruption magnitude: a few hundred to a few thousand rupees, in
#: paise. Unrelated to any ledger row -- a bank-side deduction or miskey is
#: not sized to any particular payment or fee in the batch it damages.
_MIN_DELTA_PAISE = 50_000       # Rs 500
_MAX_DELTA_PAISE = 500_000      # Rs 5,000


@dataclass(frozen=True, slots=True)
class MispostTruth:
    """What the GENERATOR knows about the corruption. Ground truth only --
    never written to `bank_statement.csv`, and never derived from anything
    outside the `Payout` this corruption started from.
    """

    payout_index: int
    true_amount_paise: int
    bank_reported_amount_paise: int
    delta_paise: int          # bank_reported - true, signed
    kind: str = "mispost"


def plant_mispost(
    payouts: list[Payout],
    index: int,
    rng: random.Random,
    delta_paise: int | None = None,
) -> tuple[list[Payout], MispostTruth | None]:
    """Replace `payouts[index]`'s amount with a wrong-bank-side amount.

    Returns a NEW list (the input is not mutated) and either a `MispostTruth`
    record, or `None` if no honest corruption could be constructed for this
    input -- mirroring `plant_false_composition`'s discipline. The caller
    must handle `None` by shipping without the plant, never by forcing one.
    """
    if not payouts or not (0 <= index < len(payouts)):
        return list(payouts), None

    target = payouts[index]
    other_true_amounts = {p.amount_paise for i, p in enumerate(payouts)
                          if i != index}

    if delta_paise is None:
        magnitude = rng.randrange(_MIN_DELTA_PAISE, _MAX_DELTA_PAISE)
        delta_paise = rng.choice([-1, 1]) * magnitude

    corrupted = target.amount_paise + delta_paise
    if corrupted <= 0:
        # a short-credit deduction that would go negative is not honest --
        # flip the sign rather than force it.
        delta_paise = -delta_paise
        corrupted = target.amount_paise + delta_paise
        if corrupted <= 0:
            return list(payouts), None

    if corrupted == target.amount_paise or corrupted in other_true_amounts:
        # either a no-op, or the corrupted amount happens to equal some
        # OTHER real settlement's true payout -- which would make the wrong
        # line look like a legitimate, unrelated credit rather than a
        # contradiction. Decline rather than force a different delta that
        # happens to avoid it; the caller ships without the plant.
        return list(payouts), None

    new_payouts = list(payouts)
    new_payouts[index] = Payout(amount_paise=corrupted,
                                initiated_at=target.initiated_at)

    truth = MispostTruth(
        payout_index=index,
        true_amount_paise=target.amount_paise,
        bank_reported_amount_paise=corrupted,
        delta_paise=delta_paise,
    )
    return new_payouts, truth
