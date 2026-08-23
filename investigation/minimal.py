"""Minimal hand-built fixtures for the adversarial sweep (Task 5).

Small enough to reason about by hand: a handful of rows, one or two bank
lines. Each isolates ONE trigger. The real, unmodified cascade is run against
them via `matching.loaders.load` on a temp directory.
"""
from __future__ import annotations

import csv, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
IST = timezone(timedelta(hours=5, minutes=30))

BASE = datetime(2027, 3, 1, 10, 0, tzinfo=IST)


def ts(day: int, hour: int = 10) -> int:
    return int((BASE + timedelta(days=day)).replace(hour=hour).timestamp())


def iso(day: int) -> str:
    return (BASE + timedelta(days=day)).date().isoformat()


def rupees(paise: int) -> str:
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}{whole}.{frac:02d}"


def payment(pid, amount, day, sid=None, utr=None, settled_day=None, on_hold=False):
    return {
        "entity_id": pid, "type": "payment", "debit": 0, "credit": amount,
        "amount": amount, "currency": "INR", "fee": 0, "tax": 0,
        "on_hold": on_hold, "settled": bool(sid), "created_at": ts(day),
        "settled_at": ts(settled_day) if settled_day is not None else None,
        "settlement_id": sid, "posted_at": None, "credit_type": "default",
        "description": "Payment", "notes": {}, "payment_id": None,
        "settlement_utr": utr, "order_id": f"order_{pid}",
        "order_receipt": f"rcpt_{pid}", "method": "upi", "card_network": None,
        "card_issuer": None, "card_type": None, "dispute_id": None,
        "source_tier": "synthesized_modelled", "source_ref": "minimal fixture",
    }


def refund(rid, parent, amount, day, sid=None, utr=None, settled_day=None):
    return {
        "entity_id": rid, "type": "refund", "debit": amount, "credit": 0,
        "amount": amount, "currency": "INR", "fee": 0, "tax": 0,
        "on_hold": False, "settled": bool(sid), "created_at": ts(day),
        "settled_at": ts(settled_day) if settled_day is not None else None,
        "settlement_id": sid, "posted_at": None, "credit_type": "default",
        "description": "Refund", "notes": {}, "payment_id": parent,
        "settlement_utr": utr, "order_id": f"order_{parent}",
        "order_receipt": f"rcpt_{parent}", "method": "upi",
        "card_network": None, "card_issuer": None, "card_type": None,
        "dispute_id": None, "source_tier": "synthesized_modelled",
        "source_ref": "minimal fixture",
    }


def adjustment(aid, amount, day, direction="debit", sid=None, settled_day=None):
    return {
        "entity_id": aid, "type": "adjustment",
        "debit": amount if direction == "debit" else 0,
        "credit": 0 if direction == "debit" else amount,
        "amount": amount, "currency": "INR", "fee": 0, "tax": 0,
        "on_hold": False, "settled": bool(sid), "created_at": ts(day),
        "settled_at": ts(settled_day) if settled_day is not None else None,
        "settlement_id": sid, "posted_at": None,
        "description": "Adjustment", "notes": [], "payment_id": None,
        "settlement_utr": None, "order_id": None, "order_receipt": None,
        "method": None, "card_network": None, "card_issuer": None,
        "card_type": None, "dispute_id": None,
        "source_tier": "synthesized_modelled", "source_ref": "minimal fixture",
    }


def bank(utr, day, amount, narration=None):
    return {"utr": utr, "date": iso(day),
            "narration": narration or f"NEFT-CR-RATN0000088-RAZORPAY SOFTWARE PVT LTD-ACME RETAIL PRIVATE LIMITED-{utr}",
            "amount": rupees(amount)}


def write_case(directory: Path, rows, bank_lines):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "recon_combined.json").write_text(json.dumps(
        {"entity": "collection", "count": len(rows), "items": rows}, indent=1))
    (directory / "disputes.json").write_text(json.dumps(
        {"entity": "collection", "count": 0, "items": []}, indent=1))
    with (directory / "bank_statement.csv").open("w", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=["utr", "date", "narration", "amount"],
                           lineterminator="\n")
        w.writeheader(); w.writerows(bank_lines)
    with (directory / "erp_orders.csv").open("w", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=["order_id", "invoice_no", "gstin",
                                           "amount", "invoice_date"],
                           lineterminator="\n")
        w.writeheader()
        for row in rows:
            if row["type"] == "payment":
                w.writerow({"order_id": row["order_id"],
                            "invoice_no": f"INV/{row['entity_id']}", "gstin": "",
                            "amount": rupees(row["amount"]),
                            "invoice_date": iso(0)})
    with (directory / "gstr2b.csv").open("w", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "gstin", "invoice_no", "invoice_date", "taxable_value", "igst",
            "cgst", "sgst", "irn", "irn_generated_at", "gstr1_filing_period",
            "supplier_gstr3b_filed", "itc_availability"], lineterminator="\n")
        w.writeheader()
    return directory


def run_case(directory: Path):
    from matching import run
    from matching.loaders import load
    return run(dataset=load(directory))
