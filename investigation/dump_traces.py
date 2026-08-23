"""Run the replay over both datasets and cache the traces as JSON."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from investigation.replay import load_pair, replay, true_batch_of

OUT = Path(__file__).resolve().parent

for which in ("primary", "holdout"):
    ds, truth, result = load_pair(which)
    tb = true_batch_of(truth)
    b2b = result.bank_to_batch
    traces = replay(ds, b2b, truth, free_pool=True)
    rows_by_id = ds.rows_by_id
    payload = {
        "which": which,
        "bank_to_batch": {str(k): v for k, v in b2b.items()},
        "assigned": dict(result.stage3.assigned),
        "contested": dict(result.stage3.contested),
        "true_batch_of": tb,
        "traces": [{
            "bank_index": t.bank_index, "utr": t.utr, "amount": t.amount,
            "value_date": t.value_date.isoformat(),
            "attested_settlement": t.attested_settlement,
            "pool_size": len(t.pool_ids), "pool_ids": list(t.pool_ids),
            "engine_kind": t.engine_kind,
            "engine_rows": list(t.engine_rows),
            "closing_count": len(t.closing_subsets),
            "closing_subsets": [list(s) for s in t.closing_subsets[:60]],
            "closing_truncated": t.closing_truncated,
            "closing_status": t.closing_status,
            "free_pool_size": t.free_pool_size,
            "free_closing_count": t.free_closing_count,
            "free_truncated": t.free_truncated,
            "consumed_rows": list(t.consumed_rows),
            "consumption_reason": t.consumption_reason,
        } for t in traces],
        "rows": {rid: {"type": r["type"], "credit": r["credit"],
                       "debit": r["debit"], "created_at": r["created_at"],
                       "settlement_id": r["settlement_id"],
                       "settlement_utr": r["settlement_utr"]}
                 for rid, r in rows_by_id.items()},
    }
    (OUT / f"traces_{which}.json").write_text(json.dumps(payload, indent=1))
    print(f"wrote traces_{which}.json  ({len(traces)} bank lines)")
