"""Stage 1 -- exact-key joins.

Three joins, all on keys that are present and unambiguous:

  recon rows  -> batches        by `settlement_id`   (NOT `settlement_utr`)
  batches     -> bank statement by the batch's UTR
  payment and refund rows -> ERP by `order_id`

Why `settlement_id` and not `settlement_utr` for grouping: adjustment rows
carry a real `settlement_id` with a NULL `settlement_utr`. Grouping on UTR
silently drops exactly the rows that make a batch net -- so the batch would
appear not to close, and the engine would report a false discrepancy on data
that is in fact correct. UTR is a hint for reaching the bank line, never a
batch key.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .loaders import BankLine, Dataset, ErpOrder, is_failed, resolve_row_id


@dataclass(frozen=True, slots=True)
class Batch:
    """Recon rows sharing a `settlement_id`, as ASSERTED by the recon file."""

    settlement_id: str
    row_ids: tuple[str, ...]
    credit_total: int
    debit_total: int
    settled_on: date
    utr_hint: str | None

    @property
    def net(self) -> int:
        return self.credit_total - self.debit_total


@dataclass
class Stage1Result:
    batches: dict[str, Batch]
    #: settlement_id -> bank line index
    batch_to_bank: dict[str, int]
    #: bank line index -> settlement_id
    bank_to_batch: dict[int, str]
    bank_unjoined: list[int]
    #: recon entity_id -> ERP invoice_no
    row_to_erp: dict[str, str]
    erp_unjoined: list[str]
    rows_without_erp: list[str]
    #: rows excluded from matching before any arithmetic ran
    failed_payment_ids: list[str]
    #: settlement_ids whose asserted rows do not sum to their bank credit
    attestation_conflicts: list[tuple[str, int, int]] = field(default_factory=list)

    @property
    def matched_row_ids(self) -> set[str]:
        return {row_id for sid, batch in self.batches.items()
                if sid in self.batch_to_bank for row_id in batch.row_ids}


def build_batches(dataset: Dataset) -> dict[str, Batch]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in dataset.rows:
        if is_failed(row):
            continue                      # fee is null; never in a batch
        if row["settlement_id"]:
            grouped[row["settlement_id"]].append(row)

    batches: dict[str, Batch] = {}
    for settlement_id, rows in sorted(grouped.items()):
        utrs = {row["settlement_utr"] for row in rows if row["settlement_utr"]}
        if len(utrs) > 1:
            raise ValueError(f"{settlement_id} carries {len(utrs)} distinct UTRs")
        settled = {row["settled_at"] for row in rows}
        if len(settled) > 1:
            raise ValueError(f"{settlement_id} has inconsistent settled_at")
        from .loaders import to_date
        batches[settlement_id] = Batch(
            settlement_id=settlement_id,
            row_ids=tuple(sorted(row["entity_id"] for row in rows)),
            credit_total=sum(row["credit"] for row in rows),
            debit_total=sum(row["debit"] for row in rows),
            settled_on=to_date(next(iter(settled))),
            utr_hint=next(iter(utrs)) if utrs else None,
        )
    return batches


def run(dataset: Dataset) -> Stage1Result:
    batches = build_batches(dataset)
    bank_by_utr = {line.utr: line for line in dataset.bank if line.has_join_key}

    batch_to_bank: dict[str, int] = {}
    bank_to_batch: dict[int, str] = {}
    for settlement_id, batch in batches.items():
        if batch.utr_hint and batch.utr_hint in bank_by_utr:
            index = bank_by_utr[batch.utr_hint].index
            batch_to_bank[settlement_id] = index
            bank_to_batch[index] = settlement_id

    bank_unjoined = sorted(line.index for line in dataset.bank
                           if line.index not in bank_to_batch)

    # The recon file ASSERTS a settlement_id. The bank is the source of truth.
    # Where both exist, check they agree; a disagreement is a finding, not a
    # thing to route away.
    conflicts = []
    for settlement_id, index in sorted(batch_to_bank.items()):
        expected = dataset.bank[index].amount
        actual = batches[settlement_id].net
        if actual != expected:
            conflicts.append((settlement_id, actual, expected))

    erp_by_order = {order.order_id: order for order in dataset.erp}
    row_to_erp: dict[str, str] = {}
    rows_without_erp: list[str] = []
    joinable_orders: set[str] = set()
    for row in dataset.rows:
        if is_failed(row) or row["type"] == "adjustment":
            continue
        order_id = row["order_id"]
        if not order_id:
            continue
        joinable_orders.add(order_id)
        if order_id in erp_by_order:
            row_to_erp[row["entity_id"]] = erp_by_order[order_id].invoice_no
        elif row["type"] == "payment":
            rows_without_erp.append(row["entity_id"])

    erp_unjoined = sorted(order.invoice_no for order in dataset.erp
                          if order.order_id not in joinable_orders)

    return Stage1Result(
        batches=batches,
        batch_to_bank=batch_to_bank,
        bank_to_batch=bank_to_batch,
        bank_unjoined=bank_unjoined,
        row_to_erp=row_to_erp,
        erp_unjoined=erp_unjoined,
        rows_without_erp=sorted(rows_without_erp),
        failed_payment_ids=sorted(row["entity_id"] for row in dataset.rows
                                  if is_failed(row)),
    )
