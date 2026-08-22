#!/usr/bin/env python3
"""PART B seeding, via the empirically-verified ajax + mocksharp path."""
import json, time
from common import load_env, basic, http, body_of, ok, ROOT, RAW
from pay import create_order, pay, refund, API

KID, SEC = load_env()
AUTH = basic(KID, SEC)
log = {"payments": [], "refunds": [], "failed": [], "blocked": []}

def sec(t): print(f"\n{'='*70}\n{t}\n{'='*70}")

def do(tag, amount, method="netbanking", bank="ALLA", wallet="mobikwik", succeed=True):
    o = create_order(AUTH, amount, tag)
    if not o:
        log["blocked"].append((tag, "order failed")); return None
    p = pay(KID, o, amount, method, bank, wallet, succeed, tag=tag)
    if not p:
        log["blocked"].append((tag, f"{method} payment path failed")); return None
    r = http("GET", f"{API}/payments/{p}", auth=AUTH, tag=f"status_{tag}")
    st = body_of(r) if ok(r) else {}
    rec = {"tag": tag, "payment_id": p, "order_id": o, "amount": amount,
           "method": method, "status": st.get("status"), "fee": st.get("fee"),
           "tax": st.get("tax"), "bank": st.get("bank"), "wallet": st.get("wallet")}
    (log["payments"] if st.get("status") == "captured" else log["failed"]).append(rec)
    print(f"  {tag}: {p} status={st.get('status')} fee={st.get('fee')} tax={st.get('tax')}")
    return p if st.get("status") == "captured" else None

sec("(a) SIMPLE 1:1")
do("a_simple", 100000)

sec("(b) FULL REFUND BEFORE SETTLEMENT")
p = do("b_fullrefund", 250000)
if p:
    r = refund(AUTH, p, tag="b_full"); log["refunds"].append(body_of(r) if ok(r) else {"err": body_of(r)})
    print(f"  refund: {body_of(r).get('id') if ok(r) else body_of(r)}")

sec("(d) PARTIAL REFUND (40%)")
p = do("d_partialrefund", 500000)
if p:
    r = refund(AUTH, p, 200000, tag="d_partial"); log["refunds"].append(body_of(r) if ok(r) else {"err": body_of(r)})
    print(f"  refund: {body_of(r).get('id') if ok(r) else body_of(r)}")

sec("(c) SUBSET-SUM: 5 awkward amounts + a mid-window refund")
subs = []
for i, amt in enumerate([133700, 289900, 415000, 76400, 198300]):
    q = do(f"c_subset{i}", amt, bank=["ALLA", "CBIN", "CNRB", "CSBK", "DCBL"][i])
    if q: subs.append((q, amt))
if len(subs) >= 3:
    r = refund(AUTH, subs[2][0], 150000, tag="c_mid")
    log["refunds"].append(body_of(r) if ok(r) else {"err": body_of(r)})
    print(f"  mid-window refund on {subs[2][0]}: {body_of(r).get('id') if ok(r) else body_of(r)}")

sec("(f) MULTIPLE PAYMENT METHODS")
do("f_wallet_mobikwik", 111100, method="wallet", wallet="mobikwik")
do("f_wallet_olamoney", 122200, method="wallet", wallet="olamoney")
do("f_wallet_airtel",   133300, method="wallet", wallet="airtelmoney")
do("f_nb_barb",         144400, bank="BARB_R")
do("f_nb_deut",         155500, bank="DEUT")

sec("(h) FAILED PAYMENT")
do("h_failed", 90000, succeed=False)

sec("BALANCE / SETTLEMENTS AFTER SEEDING")
http("GET", f"{API}/balance", auth=AUTH, tag="balance_after_seed")
http("GET", f"{API}/settlements?count=100", auth=AUTH, tag="settlements_after_seed")

(ROOT / "seed2_log.json").write_text(json.dumps(log, indent=2))
sec("SUMMARY")
print(f"captured: {len(log['payments'])}  failed: {len(log['failed'])}  refunds: {len(log['refunds'])}  blocked: {len(log['blocked'])}")
for b in log["blocked"]: print("  BLOCKED", b)
