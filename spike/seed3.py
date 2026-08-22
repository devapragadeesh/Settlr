#!/usr/bin/env python3
"""Remaining Part B scenarios: (f) methods, (h) failed. Run after seed2.py."""
import json
from common import load_env, basic, http, body_of, ok, ROOT
from pay import create_order, pay, refund, API
KID, SEC = load_env(); AUTH = basic(KID, SEC)
out = []
def do(tag, amount, method="netbanking", bank="ALLA", wallet="mobikwik", succeed=True):
    o = create_order(AUTH, amount, tag)
    if not o: return None
    p = pay(KID, o, amount, method, bank, wallet, succeed, tag=tag)
    if not p: print(f"  {tag}: BLOCKED"); return None
    r = http("GET", f"{API}/payments/{p}", auth=AUTH, tag=f"status_{tag}")
    st = body_of(r) if ok(r) else {}
    print(f"  {tag}: {p} status={st.get('status')} method={st.get('method')} fee={st.get('fee')} tax={st.get('tax')}")
    out.append({"tag": tag, "pid": p, "status": st.get("status"), "fee": st.get("fee"), "tax": st.get("tax"), "amount": amount})
    return p if st.get("status") == "captured" else None

print("(f) METHODS")
do("f_wallet_mobikwik", 111100, method="wallet", wallet="mobikwik")
do("f_wallet_olamoney", 122200, method="wallet", wallet="olamoney")
do("f_wallet_airtel",   133300, method="wallet", wallet="airtelmoney")
do("f_nb_barb",         144400, bank="BARB_R")
do("f_nb_deut",         155500, bank="DEUT")
print("(h) FAILED")
do("h_failed", 90000, succeed=False)
http("GET", f"{API}/balance", auth=AUTH, tag="balance_after_seed")
http("GET", f"{API}/settlements?count=100", auth=AUTH, tag="settlements_after_seed")
(ROOT / "seed3_log.json").write_text(json.dumps(out, indent=2))
print("done")
