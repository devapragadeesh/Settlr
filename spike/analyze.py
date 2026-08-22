#!/usr/bin/env python3
"""Verifies the arithmetic identities the recon engine rests on, against real
captured recon rows, and reports settlement_id grouping behaviour.

  usage: python3 analyze.py raw/0NN_rest_recon_YYYY_MM.json   (or any file with {"items":[...]})

Identity 1 is tested as two COMPETING hypotheses rather than assumed, because
the project brief and Razorpay's payment-entity docs disagree:

  H_inclusive (docs, and verified on payment entities):  credit = amount - fee
      -> `fee` is "Fee (including GST) charged by Razorpay"; `tax` is a
         breakdown line INSIDE fee, not an additional charge.
  H_disjoint  (the brief's assumption):                  credit = amount - fee - tax

Whichever holds on real recon rows wins. Do not hard-code either.

Identity 2 (per batch):   sum(credit) - sum(debit) = settlement.amount
"""
import json, sys, collections, pathlib

def load_items(path):
    d = json.loads(pathlib.Path(path).read_text())
    # accept either a raw evidence file or a bare API response
    for cand in (d, d.get("response", {}).get("body") if isinstance(d, dict) else None):
        if isinstance(cand, dict) and isinstance(cand.get("items"), list):
            return cand["items"]
    raise SystemExit(f"no 'items' array found in {path}")

def main(paths):
    items = []
    for p in paths:
        items += load_items(p)
    print(f"rows: {len(items)}\n")

    # ---- field presence census -----------------------------------------
    DOCUMENTED = ["entity_id","type","debit","credit","amount","currency","fee","tax",
                  "on_hold","settled","created_at","settled_at","settlement_id","description",
                  "notes","payment_id","settlement_utr","order_id","order_receipt","method",
                  "card_network","card_issuer","card_type","dispute_id"]
    seen = collections.Counter()
    nonnull = collections.Counter()
    for it in items:
        for k, v in it.items():
            seen[k] += 1
            if v not in (None, "", [], {}):
                nonnull[k] += 1
    print("FIELD CENSUS  (present / non-null / of %d rows)" % len(items))
    for k in DOCUMENTED:
        flag = "" if seen[k] else "   <-- DOCUMENTED BUT ABSENT"
        print(f"  {k:18} {seen[k]:4} {nonnull[k]:4}{flag}")
    undoc = [k for k in seen if k not in DOCUMENTED]
    for k in sorted(undoc):
        print(f"  {k:18} {seen[k]:4} {nonnull[k]:4}   <-- UNDOCUMENTED FIELD")

    # ---- identity 1: two competing hypotheses -----------------------------
    print("\nIDENTITY 1  (competing hypotheses, neither assumed)")
    bytype = collections.Counter(it.get("type") for it in items)
    print(f"  rows by type: {dict(bytype)}")

    inc_ok = inc_bad = dis_ok = dis_bad = 0
    examples = []
    for it in items:
        a, f, x = it.get("amount", 0), it.get("fee", 0), it.get("tax", 0)
        c = it.get("credit", 0)
        if not c:
            continue
        if c == a - f:
            inc_ok += 1
        else:
            inc_bad += 1
        if c == a - f - x:
            dis_ok += 1
        else:
            dis_bad += 1
        if x == 0 and len(examples) < 3:
            examples.append(it.get("entity_id"))
    print(f"  H_inclusive  credit = amount - fee        : {inc_ok} hold / {inc_bad} fail")
    print(f"  H_disjoint   credit = amount - fee - tax  : {dis_ok} hold / {dis_bad} fail")
    if inc_ok and dis_ok and inc_bad == dis_bad == 0:
        print("  INDECISIVE: every credit row has tax == 0, so both hypotheses fit.")
        print(f"             degenerate rows e.g. {examples}")
    elif inc_bad == 0 and dis_bad > 0:
        print("  -> H_inclusive WINS. fee is tax-inclusive; use credit = amount - fee.")
    elif dis_bad == 0 and inc_bad > 0:
        print("  -> H_disjoint WINS. fee and tax are additive; the brief was right.")
    else:
        print("  -> NEITHER holds cleanly. Inspect rows manually before modelling.")

    # debit rows: same question, opposite sign
    debits = [it for it in items if it.get("debit") and it.get("fee")]
    if debits:
        inside = sum(1 for it in debits if it["debit"] == it["amount"] + it["fee"])
        outside = sum(1 for it in debits if it["debit"] == it["amount"] + it["fee"] + it.get("tax", 0))
        print(f"  debit rows with fee: tax-INSIDE-fee={inside}  tax-OUTSIDE-fee={outside}  (of {len(debits)})")

    # rows matching no reading at all
    weird = [it.get("entity_id") for it in items
             if it.get("debit") and it["debit"] not in
             (it.get("amount", 0), it.get("amount", 0) + it.get("fee", 0),
              it.get("amount", 0) + it.get("fee", 0) + it.get("tax", 0))]
    if weird:
        print(f"  UNEXPLAINED debit rows: {weird[:20]}")

    # ---- identity 2 + grouping -----------------------------------------
    print("\nIDENTITY 2  per settlement_id:  sum(credit) - sum(debit) = net paid out")
    g = collections.defaultdict(list)
    for it in items:
        g[it.get("settlement_id")].append(it)
    for sid, rows in sorted(g.items(), key=lambda kv: -len(kv[1])):
        cr = sum(r.get("credit", 0) for r in rows)
        db = sum(r.get("debit", 0) for r in rows)
        types = collections.Counter(r.get("type") for r in rows)
        utr = {r.get("settlement_utr") for r in rows}
        print(f"  {sid}: {len(rows):3} rows {dict(types)}  Scredit={cr} Sdebit={db} net={cr-db}  utr={utr}")

    # ---- the money question: is settlement grouping ever non-trivial? ---
    print("\nSUBSET-SUM EVIDENCE")
    unsettled = [it for it in items if not it.get("settled") or not it.get("settlement_id")]
    print(f"  rows with no settlement_id / settled=false: {len(unsettled)}")
    days = collections.defaultdict(set)
    import datetime
    for it in items:
        if it.get("created_at") and it.get("settlement_id"):
            d = datetime.datetime.fromtimestamp(it["created_at"], datetime.timezone.utc).strftime("%Y-%m-%d")
            days[d].add(it["settlement_id"])
    split = {d: s for d, s in days.items() if len(s) > 1}
    if split:
        print("  SAME-DAY payments landing in DIFFERENT settlements (the key evidence):")
        for d, s in sorted(split.items()):
            print(f"    {d}: {len(s)} settlements {sorted(s)}")
    else:
        print("  no same-day split found in this sample -> subset-sum NOT yet demonstrated")

    # cross-month
    xm = []
    for it in items:
        ca, sa = it.get("created_at"), it.get("settled_at")
        if ca and sa:
            import datetime as dt
            if dt.datetime.fromtimestamp(ca, dt.timezone.utc).month != dt.datetime.fromtimestamp(sa, dt.timezone.utc).month:
                xm.append(it.get("entity_id"))
    print(f"\nCROSS-MONTH rows (created_at month != settled_at month): {len(xm)} {xm[:10]}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
