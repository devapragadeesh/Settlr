"""TASK 6 -- measure each candidate fix on BOTH datasets. No engine changes.

Re-implements stage 3's loop with a policy switch, so each remediation can be
costed without touching `matching/`. The baseline policy reproduces the frozen
engine exactly, which is asserted before any variant is trusted.
"""
from __future__ import annotations

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matching.loaders import load
from matching.model import (Ambiguous, Decomposition, Determinate, Unresolved,
                            resolve_from_candidates)
from matching.stage3_solver import (ENUMERATION_CAP, build_pool,
                                    enumerate_decompositions,
                                    find_zero_net_groups)
from investigation.replay import all_closing_subsets


def policy_run(dataset, bank_to_batch, *,
               unfiltered_closure=False,
               require_attested_for_determinate=False,
               utr_contradiction_veto=False,
               require_attested_composition=False,
               consume_only_on_attestation=False,
               reversal_prepass=False):
    """stage3_solver.run with switches. Defaults == the frozen engine."""
    zero_net = find_zero_net_groups(dataset.rows)
    excluded = {g.payment_id for g in zero_net}
    for g in zero_net:
        excluded.update(g.refund_ids)
    rows_by_id = {r["entity_id"]: r for r in dataset.rows}

    # solver-visible: what each settlement's rows declare as their UTR
    sid_utr, sid_rows = {}, {}
    for rid, r in rows_by_id.items():
        if r["settlement_id"]:
            sid_rows.setdefault(r["settlement_id"], set()).add(rid)
            if r["settlement_utr"]:
                sid_utr[r["settlement_id"]] = r["settlement_utr"]

    reversed_utrs = set()
    if reversal_prepass:
        # a DEBIT whose amount mirrors an earlier CREDIT with the same UTR
        credits = {}
        for line in sorted(dataset.bank, key=lambda b: (b.value_date, b.index)):
            if line.amount > 0 and line.utr:
                credits[line.utr] = line
            elif line.amount < 0 and line.utr in credits:
                if credits[line.utr].amount == -line.amount:
                    reversed_utrs.add(line.utr)

    assigned, contested, kinds = {}, {}, {}
    consumed = set()
    for line in sorted(dataset.bank, key=lambda b: (b.value_date, b.index)):
        pool = build_pool(dataset, line.value_date, consumed, excluded)

        if unfiltered_closure:
            subsets, truncated, _, _ = all_closing_subsets(
                pool, line.amount, cap=ENUMERATION_CAP)
            truncated = len(subsets) >= ENUMERATION_CAP
        else:
            subsets, truncated, _, _ = enumerate_decompositions(
                pool, line.amount, ENUMERATION_CAP)

        candidates = [Decomposition.build(rows_by_id, s) for s in subsets]
        resolution = resolve_from_candidates(
            candidates, bank_amount=line.amount, truncated=truncated,
            method="policy", pool_size=len(pool),
            enumeration_cap=ENUMERATION_CAP)

        attested = bank_to_batch.get(line.index)

        if reversal_prepass and line.utr in reversed_utrs and line.amount > 0:
            resolution = Unresolved(reason="credit_later_reversed",
                                    pool_size=len(pool), method="prepass")

        if isinstance(resolution, Determinate):
            chosen = set(resolution.decomposition.row_ids)
            declared = {rows_by_id[r]["settlement_id"] for r in chosen
                        if rows_by_id[r]["settlement_id"]}
            declared_utrs = {sid_utr[s] for s in declared if s in sid_utr}

            refuse = None
            if require_attested_for_determinate and not attested:
                refuse = "no_attestation_for_this_bank_line"
            if (utr_contradiction_veto and line.utr and declared_utrs
                    and line.utr not in declared_utrs):
                refuse = "rows_declare_a_different_utr"
            if require_attested_composition and attested:
                if chosen != sid_rows.get(attested, set()):
                    refuse = "decomposition_contradicts_attested_composition"
            if require_attested_composition and not attested:
                refuse = refuse or "no_attestation_to_corroborate_against"
            if refuse:
                resolution = Unresolved(reason=refuse, pool_size=len(pool),
                                        method="policy")

        kinds[line.index] = type(resolution).__name__
        if isinstance(resolution, Determinate):
            for rid in resolution.decomposition.row_ids:
                assigned[rid] = line.index
        elif isinstance(resolution, Ambiguous):
            for rid in resolution.certain_rows:
                assigned[rid] = line.index
            for rid in resolution.contested_rows:
                contested[rid] = line.index

        if attested:
            consumed |= {r["entity_id"] for r in dataset.rows
                         if r["settlement_id"] == attested}
        elif isinstance(resolution, Determinate) and not consume_only_on_attestation:
            consumed |= set(resolution.decomposition.row_ids)

    return assigned, contested, kinds


def accounting(dataset, truth, bank_to_batch, assigned, contested):
    true_of = {}
    for b in truth["batches"]:
        for rid in b["credit_ids"] + b["debit_ids"]:
            true_of[rid] = b["settlement_id"]
    ok = wrong = declined = missed = left = wrongly = 0
    for row in dataset.rows:
        rid = row["entity_id"]
        actual = true_of.get(rid)
        if actual:
            if rid in assigned:
                if bank_to_batch.get(assigned[rid]) == actual:
                    ok += 1
                else:
                    wrong += 1
            elif rid in contested:
                declined += 1
            else:
                missed += 1
        else:
            if rid in assigned:
                wrongly += 1
            else:
                left += 1
    settled = ok + wrong + declined + missed
    return {"placed_correctly": ok, "placed_incorrectly": wrong,
            "declined": declined, "missed": missed,
            "wrongly_placed": wrongly, "truly_settled": settled,
            "match_rate": ok / settled if settled else 0.0}
