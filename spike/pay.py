"""Working test-mode payment path, discovered empirically 2026-08-22.

  POST /v1/payments/create/ajax        -> 'mocksharp' mock-gateway handoff
  POST /v1/gateway/mocksharp/payment   -> mock bank page (success/fail buttons)
  POST .../payment/submit  success=S|F -> authorizes or fails the payment

Cards are NOT usable here: the ajax endpoint returns a bare 403 Forbidden HTML
page (WAF) whenever card[] fields are present, with or without browser headers.
Netbanking and wallet carry no card data and pass.
"""
import re, urllib.parse
from common import http, body_of, ok

API = "https://api.razorpay.com/v1"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

def create_order(auth, amount, receipt, notes=None):
    r = http("POST", f"{API}/orders", auth=auth, tag=f"order_{receipt}",
             body={"amount": amount, "currency": "INR", "receipt": receipt,
                   "notes": notes or {"scenario": receipt}})
    return body_of(r)["id"] if ok(r) else None

def pay(kid, order_id, amount, method="netbanking", bank="ALLA", wallet="mobikwik",
        succeed=True, tag=""):
    """Drive one payment all the way to authorized/failed. Returns payment_id or None."""
    form = {"key_id": kid, "amount": amount, "currency": "INR", "order_id": order_id,
            "email": "spike@example.com", "contact": "9999999999", "method": method,
            "_[library]": "checkoutjs"}
    if method == "netbanking":
        form["bank"] = bank
    elif method == "wallet":
        form["wallet"] = wallet

    r = http("POST", f"{API}/payments/create/ajax", body=urllib.parse.urlencode(form),
             extra_headers=FORM, tag=f"ajax_{method}_{tag}")
    b = body_of(r)
    if not ok(r) or not isinstance(b, dict) or "request" not in b:
        return None
    pid, gw = b.get("payment_id"), b.get("gateway")
    content = dict(b["request"]["content"])
    content["gateway"] = gw

    r2 = http("POST", b["request"]["url"], body=urllib.parse.urlencode(content),
              extra_headers=FORM, tag=f"mockpage_{tag}")
    html = body_of(r2)
    if not isinstance(html, str):
        return None
    m = re.search(r'action="([^"]*mocksharp[^"]*submit[^"]*)"', html)
    cb = re.search(r'name="callback_url" value="([^"]*)"', html)
    if not (m and cb):
        return None

    r3 = http("POST", m.group(1).replace("&amp;", "&"),
              body=urllib.parse.urlencode({"success": "S" if succeed else "F",
                                           "language_code": "en",
                                           "callback_url": cb.group(1)}),
              extra_headers=FORM, tag=f"mocksubmit_{tag}")
    return pid

def refund(auth, pid, amount=None, tag=""):
    body = {"speed": "normal"}
    if amount:
        body["amount"] = amount
    return http("POST", f"{API}/payments/{pid}/refund", auth=auth, body=body,
                tag=f"refund_{tag}")
