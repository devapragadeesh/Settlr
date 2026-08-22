#!/usr/bin/env python3
"""Reproducible evidence for the fee/tax finding, run against live test-mode data.

Tests two competing readings of the payment entity's fee/tax pair:
  H_inclusive : fee already contains tax  -> net = amount - fee
  H_disjoint  : fee and tax are additive  -> net = amount - fee - tax
and settles it against GET /v1/balance, which cannot be argued with.
"""
from common import load_env, basic, http, body_of, ok
API = "https://api.razorpay.com/v1"
KID, SEC = load_env(); AUTH = basic(KID, SEC)

pays = body_of(http("GET", f"{API}/payments?count=100", auth=AUTH, tag="verify_payments"))["items"]
refs = body_of(http("GET", f"{API}/refunds?count=100", auth=AUTH, tag="verify_refunds"))["items"]
bal = body_of(http("GET", f"{API}/balance", auth=AUTH, tag="verify_balance"))["balance"]

fee_rows = [p for p in pays if p.get("fee")]
print(f"\n{len(pays)} payments, {len(fee_rows)} with a fee, {len(refs)} refunds\n")

print(f"{'amount':>9}{'fee':>7}{'tax':>6}{'fee-tax':>9}{'(fee-tax)/amt':>15}{'tax/(fee-tax)':>15}")
exact = True
for p in sorted(fee_rows, key=lambda x: x["amount"]):
    a, f, t = p["amount"], p["fee"], p["tax"]
    base = f - t
    rate = base * 100 / a
    gst = t * 100 / base
    if abs(rate - 2.0) > 1e-9:
        exact = False
    print(f"{a:9}{f:7}{t:6}{base:9}{rate:14.6f}%{gst:14.4f}%")

print(f"\n(fee-tax)/amount is exactly 2.000000% on every row: {exact}")

live = [p for p in pays if p["status"] in ("captured", "refunded")]
inc = sum(p["amount"] - p["fee"] for p in live)
dis = sum(p["amount"] - p["fee"] - p["tax"] for p in live)
r = sum(x["amount"] for x in refs)
print(f"\n{'':22}{'predicted balance':>20}{'actual':>12}{'delta':>12}")
print(f"{'H_inclusive (amt-fee)':22}{inc - r:20}{bal:12}{bal - (inc - r):12}")
print(f"{'H_disjoint  (-fee-tax)':22}{dis - r:20}{bal:12}{bal - (dis - r):12}")
print(f"\nsum of tax column = {sum(p['tax'] for p in live)}  (exactly the gap between the two)")
winner = "H_inclusive" if bal == inc - r else "H_disjoint" if bal == dis - r else "NEITHER"
print(f"\nVERDICT: {winner}")
if winner == "H_inclusive":
    print("  fee is tax-inclusive -> correct identity is  credit = amount - fee")
    print("  Razorpay payment-entity docs agree: fee = 'Fee (including GST) charged by Razorpay.'")
