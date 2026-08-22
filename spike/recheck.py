#!/usr/bin/env python3
"""Re-poll for a settlement. Run daily until 2026-08-27 (T+5 from seeding).

Seeding completed 2026-08-22. Default PG settlement is T+2 working days, so the
earliest plausible settlement is 2026-08-25 (Mon). If nothing has settled by
2026-08-27, treat 'test mode never settles' as confirmed.
"""
import datetime, json
from common import load_env, basic, http, body_of, ok
API = "https://api.razorpay.com/v1"
KID, SEC = load_env(); AUTH = basic(KID, SEC)
now = datetime.datetime.now()
s = http("GET", f"{API}/settlements?count=100", auth=AUTH, tag="recheck_settlements")
r = http("GET", f"{API}/settlements/recon/combined?year={now.year}&month={now.month:02d}",
         auth=AUTH, tag="recheck_recon")
b = http("GET", f"{API}/balance", auth=AUTH, tag="recheck_balance")
ns = body_of(s).get("count") if ok(s) else "ERR"
nr = body_of(r).get("count") if ok(r) else "ERR"
print(f"{now:%Y-%m-%d %H:%M}  settlements={ns}  recon_rows={nr}  balance={body_of(b).get('balance')}")
if ns or nr:
    print("\n*** SETTLEMENT APPEARED. Run: python3 analyze.py raw/*recheck_recon*.json ***")
    print(json.dumps(body_of(r), indent=2)[:4000])
else:
    print("still nothing settled")
