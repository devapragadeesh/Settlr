"""corpus/sim.py must reproduce engine/simulator.py at the frozen config point.

Two implementations of one spec drift silently, and then every corpus number
measures a different rule than the frozen numbers -- so "are these comparable?"
has no answer. Code review does not close that. A differential test does.

The frozen configuration point (max_under_cap, max_pool=28, the frozen batch
times) therefore BECOMES a corpus axis point: it must reproduce the frozen
result exactly, and every other axis point is a controlled deviation from a
verified baseline rather than an unanchored new artefact.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# the frozen generator does `from simulator import ...`, so engine/ must be on
# the path too. Same mechanism holdout/generate_holdout.py uses; nothing under
# engine/ is written or patched on disk.
if str(ROOT / "engine") not in sys.path:
    sys.path.insert(0, str(ROOT / "engine"))

import generator as frozen_generator          # noqa: E402  the FROZEN generator
from engine.simulator import (AdjustmentEvent, PaymentEvent, RefundEvent,
                              SimulatorConfig, compute_fee)
from engine.simulator import simulate as frozen_simulate
from corpus.generator.sim import CorpusConfig, simulate as corpus_simulate

FROZEN_SEED = 20260822


def canon(result):
    """An id-independent projection of a simulation.

    `settlement_id`s come from the id factory and differ between runs, so
    equality is asserted over batch INDEX rather than settlement id -- and over
    everything else byte-for-byte, including the tie register.
    """
    index_of = {b.settlement_id: i for i, b in enumerate(result.batches)}
    return (
        [(b.formed_at, b.available, b.credit_ids, b.debit_ids, b.selected_credit,
          b.credit_total, b.debit_total, b.payout, b.ambiguous,
          sorted(b.tying_decompositions), b.tying_decompositions_truncated,
          b.selection_degraded, b.pool_size) for b in result.batches],
        {e: index_of[s] for e, s in result.settled_in.items()},
        dict(result.unsettled_reason),
        sorted(result.netted_out),
    )


def frozen_ledger(seed: int):
    rng = random.Random(seed)
    mk = frozen_generator.make_id_factory(rng)
    times = [frozen_generator.ts(d) for d in frozen_generator.BATCH_DATES]
    config = SimulatorConfig(batch_times=times)
    payments, refunds, adjustments, _roles, _disputes, _decoys = \
        frozen_generator.build_ledger(rng, mk)
    frozen_generator.plant_pressure(payments, refunds, adjustments, config, rng,
                                    mk, frozen_generator.PRESSURE_BATCHES)
    frozen_generator.plant_ambiguity(payments, refunds, adjustments, config, rng,
                                     mk, frozen_generator.AMBIGUITY_BATCHES)
    return payments, refunds, adjustments, times


@pytest.mark.parametrize("rule", ["max_under_cap", "fifo_under_cap"])
def test_corpus_sim_reproduces_frozen_simulator_on_the_frozen_ledger(rule):
    payments, refunds, adjustments, times = frozen_ledger(FROZEN_SEED)
    a = frozen_simulate(payments, refunds, adjustments,
                        SimulatorConfig(batch_times=times, selection_rule=rule))
    b = corpus_simulate(payments, refunds, adjustments,
                        CorpusConfig(batch_times=times, selection_rule=rule))
    assert canon(a) == canon(b)


def random_ledger(seed: int):
    """A small seeded ledger -- conformance proved on one input is not proved."""
    rng = random.Random(seed)
    base = 1781496000
    day = 86400
    payments, refunds, adjustments = [], [], []
    for i in range(rng.randint(8, 26)):
        amount = rng.randrange(10000, 900000)
        method = rng.choice(["upi", "netbanking", "card", "wallet"])
        network = rng.choice([None, "Visa", "Amex", "RuPay"]) if method == "card" else None
        card_type = rng.choice(["credit", "debit"]) if method == "card" else None
        fee, tax = compute_fee(amount, method, network, card_type)
        payments.append(PaymentEvent(
            id=f"pay_{seed}_{i:03d}", order_id=f"order_{seed}_{i:03d}",
            order_receipt=f"rcpt-{i}", amount=amount, fee=fee, tax=tax,
            method=method, created_at=base + rng.randrange(30 * day),
            captured=rng.random() > 0.05, notes={},
            card_network=network, card_type=card_type))
    for i in range(rng.randint(0, 6)):
        parent = rng.choice(payments)
        refunds.append(RefundEvent(
            id=f"rfnd_{seed}_{i:03d}", payment_id=parent.id,
            amount=rng.choice([parent.amount, parent.amount // 2]),
            created_at=parent.created_at + rng.randrange(1, 12 * day), notes={}))
    for i in range(rng.randint(0, 5)):
        adjustments.append(AdjustmentEvent(
            id=f"adj_{seed}_{i:03d}", amount=rng.randrange(500, 60000),
            created_at=base + rng.randrange(30 * day), description="adj",
            direction=rng.choice(["debit", "credit"])))
    times = [base + (7 * k + 2) * day + 41400 for k in range(5)]
    return payments, refunds, adjustments, times


@pytest.mark.parametrize("seed", range(25))
def test_corpus_sim_reproduces_frozen_simulator_on_random_ledgers(seed):
    payments, refunds, adjustments, times = random_ledger(seed)
    a = frozen_simulate(payments, refunds, adjustments,
                        SimulatorConfig(batch_times=times))
    b = corpus_simulate(payments, refunds, adjustments,
                        CorpusConfig(batch_times=times))
    assert canon(a) == canon(b)


def test_corpus_batches_carry_no_bank_reference():
    """Defect D4, asserted at the source rather than downstream: the batch
    never learns a UTR, so nothing downstream can copy one out of it."""
    payments, refunds, adjustments, times = frozen_ledger(FROZEN_SEED)
    result = corpus_simulate(payments, refunds, adjustments,
                             CorpusConfig(batch_times=times))
    assert result.batches
    assert all(b.utr == "" for b in result.batches)


def test_frozen_simulator_derives_its_utr_and_this_test_proves_it():
    """The defect this file's existence is justified by, asserted directly.

    If this ever fails, `engine/simulator.py` was modified and the freeze is
    broken -- which is a much larger finding than a corpus test failing.
    """
    payments, refunds, adjustments, times = frozen_ledger(FROZEN_SEED)
    result = frozen_simulate(payments, refunds, adjustments,
                             SimulatorConfig(batch_times=times))
    assert result.batches
    assert all(b.utr == f"{b.formed_at}{b.settlement_id[-6:]}"
               for b in result.batches)
