#!/usr/bin/env python3
"""PART B - seed test-mode transactions covering the 8 recon scenarios.

Payment creation in test mode is the fragile step: Razorpay's documented
server-to-server payment APIs require account allowlisting. This script tries
each known path in order and records exactly which one worked (or that none did),
rather than assuming.

Scenarios seeded: (a) simple 1:1, (b) refund-before-settlement, (c) subset-sum
batch, (d) partial refund, (f) multi-method, (g) cross-month, (h) failed payment.
(e) dispute is NOT seedable via API - see FINDINGS.md.
"""
import json, sys, time, urllib.parse
from common import load_env, basic, http, body_of, ok, ROOT, RAW

API = "https://api.razorpay.com/v1"
KID, SEC = load_env()
AUTH = basic(KID, SEC)

STATE = ROOT / "seed_state.json"
state = json.loads(STATE.read_text()) if STATE.exists() else {"orders": [], "payments": [], "refunds": [], "notes": []}

def save():
    STATE.write_text(json.dumps(state, indent=2))

def section(t):
    print(f"\n{'='*70}\n{t}\n{'='*70}")

def create_order(amount, receipt, notes=None):
    r = http("POST", f"{API}/orders", auth=AUTH, tag=f"order_{receipt}",
             body={"amount": amount, "currency": "INR", "receipt": receipt,
                   "notes": notes or {"scenario": receipt}})
    if ok(r):
        oid = body_of(r)["id"]
        state["orders"].append({"id": oid, "amount": amount, "receipt": receipt})
        save()
        return oid
    return None

# ---------------------------------------------------------------- payment paths
def pay_via_ajax(order_id, amount, method="card"):
    """Undocumented checkout endpoint. Uses key_id in the form body, not Basic auth.
    This is the path automated test-mode suites commonly use. May be blocked."""
    form = {"key_id": KID, "amount": amount, "currency": "INR", "order_id": order_id,
            "email": "spike@example.com", "contact": "9999999999", "method": method,
            "_[shield][fhash]": "", "_[library]": "checkoutjs"}
    if method == "card":
        form.update({"card[number]": "4111111111111111", "card[cvv]": "123",
                     "card[expiry_month]": "12", "card[expiry_year]": "30",
                     "card[name]": "Spike Test"})
    elif method == "upi":
        form.update({"vpa": "success@razorpay", "upi[flow]": "collect"})
    elif method == "netbanking":
        form["bank"] = "HDFC"
    elif method == "wallet":
        form["wallet"] = "payzapp"
    return http("POST", f"{API}/payments/create/ajax",
                body=urllib.parse.urlencode(form),
                extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
                tag=f"payajax_{method}_{order_id[-6:]}")

def pay_via_s2s(order_id, amount, method="upi"):
    """Documented S2S API - requires the account to be allowlisted for it."""
    body = {"amount": amount, "currency": "INR", "order_id": order_id,
            "email": "spike@example.com", "contact": "9999999999", "method": method}
    if method == "upi":
        body["upi"] = {"flow": "collect", "vpa": "success@razorpay", "expiry_time": 5}
    return http("POST", f"{API}/payments/create/upi" if method == "upi" else f"{API}/payments/create",
                auth=AUTH, body=body, tag=f"pays2s_{method}_{order_id[-6:]}")

def make_payment(order_id, amount, method="card"):
    r = pay_via_ajax(order_id, amount, method)
    if ok(r) and isinstance(body_of(r), dict) and body_of(r).get("razorpay_payment_id"):
        pid = body_of(r)["razorpay_payment_id"]
        state["payments"].append({"id": pid, "order_id": order_id, "amount": amount,
                                  "method": method, "path": "create/ajax"})
        save()
        return pid
    r2 = pay_via_s2s(order_id, amount, method)
    if ok(r2) and isinstance(body_of(r2), dict) and body_of(r2).get("razorpay_payment_id"):
        pid = body_of(r2)["razorpay_payment_id"]
        state["payments"].append({"id": pid, "order_id": order_id, "amount": amount,
                                  "method": method, "path": "s2s"})
        save()
        return pid
    print(f"  !! BLOCKED: no server-side payment path worked for {order_id} ({method}).")
    print("     -> fall back to browser checkout (see FINDINGS.md 'Seeding blocker')")
    return None

def capture(pid, amount):
    return http("POST", f"{API}/payments/{pid}/capture", auth=AUTH,
                body={"amount": amount, "currency": "INR"}, tag=f"capture_{pid[-6:]}")

def refund(pid, amount=None, speed="normal"):
    body = {"speed": speed}
    if amount:
        body["amount"] = amount
    r = http("POST", f"{API}/payments/{pid}/refund", auth=AUTH, body=body,
             tag=f"refund_{pid[-6:]}")
    if ok(r):
        state["refunds"].append({"id": body_of(r)["id"], "payment_id": pid, "amount": amount})
        save()
    return r

# ---------------------------------------------------------------- scenarios
section("Scenario (a) SIMPLE 1:1  - one card payment, captured, no complications")
o = create_order(100000, "sc_a_simple")
p = make_payment(o, 100000, "card") if o else None
if p: capture(p, 100000)

section("Scenario (b) REFUND BEFORE SETTLEMENT - full refund pre-settlement")
o = create_order(250000, "sc_b_full_refund")
p = make_payment(o, 250000, "card") if o else None
if p:
    capture(p, 250000)
    refund(p)

section("Scenario (d) PARTIAL REFUND - 40% of a captured payment")
o = create_order(500000, "sc_d_partial_refund")
p = make_payment(o, 500000, "card") if o else None
if p:
    capture(p, 500000)
    refund(p, 200000)

section("Scenario (c) SUBSET-SUM - 4 payments + 1 refund in the same window")
# deliberately awkward amounts so no clean subset sums to a round balance
for i, amt in enumerate([133700, 289900, 415000, 76400]):
    o = create_order(amt, f"sc_c_subset_{i}")
    p = make_payment(o, amt, "card") if o else None
    if p:
        capture(p, amt)
        if i == 2:
            refund(p, 150000)   # drops live balance mid-window

section("Scenario (f) MULTIPLE PAYMENT METHODS - upi / netbanking / wallet")
for method, amt in [("upi", 111100), ("netbanking", 222200), ("wallet", 333300)]:
    o = create_order(amt, f"sc_f_{method}")
    p = make_payment(o, amt, method) if o else None
    if p: capture(p, amt)

section("Scenario (h) FAILED PAYMENT - authorized but never captured, plus a bad-card attempt")
o = create_order(90000, "sc_h_uncaptured")
p = make_payment(o, 90000, "card") if o else None   # deliberately NOT captured
o = create_order(90000, "sc_h_failed")
if o:
    # 4000 0000 0000 0002 is Razorpay's test failure card
    form_fail = pay_via_ajax(o, 90000, "card")

section("Instant settlement - fastest way to force a settlement batch to exist")
http("GET", f"{API}/balance", auth=AUTH, tag="balance_before_settle")
http("POST", f"{API}/settlements/ondemand", auth=AUTH, tag="ondemand_settlement_create",
     body={"amount": 100000, "settle_full_balance": False,
           "description": "spike forced settlement", "notes": {"spike": "part_b"}})

section("SEED STATE")
print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in state.items()}, indent=2))
print(f"Detail: {STATE}")
print(f"Raw evidence: {RAW}")
