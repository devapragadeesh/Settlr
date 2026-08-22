#!/usr/bin/env python3
"""PART A - does the official Razorpay MCP server serve test-mode data?

Probes, in order:
  1. Hosted MCP (https://mcp.razorpay.com/mcp): initialize, tools/list, then each settlement tool.
  2. Direct REST fallback for the same four operations.
Every raw request/response lands in spike/raw/ as numbered JSON.
"""
import json, sys, datetime
from common import load_env, basic, http, body_of, ok, RAW

MCP_URL = "https://mcp.razorpay.com/mcp"
API = "https://api.razorpay.com/v1"

KID, SEC = load_env()
AUTH = basic(KID, SEC)
NOW = datetime.datetime.now()
YEAR, MONTH = NOW.year, NOW.month

_mcp_id = [0]
_session = {}

def mcp(method, params=None, tag=None):
    _mcp_id[0] += 1
    payload = {"jsonrpc": "2.0", "id": _mcp_id[0], "method": method}
    if params is not None:
        payload["params"] = params
    hdrs = {"Accept": "application/json, text/event-stream"}
    hdrs.update(_session)
    rec = http("POST", MCP_URL, auth=AUTH, body=payload, extra_headers=hdrs,
               tag=tag or ("mcp_" + method.replace("/", "_")))
    sid = rec["response"]["headers"].get("Mcp-Session-Id") or rec["response"]["headers"].get("mcp-session-id")
    if sid:
        _session["Mcp-Session-Id"] = sid
    return rec

def mcp_tool(name, args, tag=None):
    return mcp("tools/call", {"name": name, "arguments": args}, tag=tag or f"mcp_tool_{name}")

def section(t):
    print(f"\n{'='*70}\n{t}\n{'='*70}")

results = {}

section("A1. Hosted MCP handshake")
init = mcp("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "settlement-spike", "version": "0.1"}})
results["mcp_initialize"] = ok(init)
if ok(init):
    mcp("notifications/initialized")   # some servers require this before tools/call
    tl = mcp("tools/list", {})
    results["mcp_tools_list"] = ok(tl)
    b = body_of(tl)
    if isinstance(b, dict):
        names = [t.get("name") for t in b.get("result", {}).get("tools", [])]
        print(f"  tools advertised ({len(names)}): {', '.join(names)}")
        results["mcp_tool_names"] = names
else:
    print("  !! MCP handshake failed - skipping MCP tool calls, going straight to REST")

if results.get("mcp_initialize"):
    section("A3a. fetch_all_settlements (MCP)")
    r = mcp_tool("fetch_all_settlements", {"count": 100})
    results["mcp_fetch_all_settlements"] = ok(r)

    section("A3b. fetch_settlement_recon_details (MCP)")
    r = mcp_tool("fetch_settlement_recon_details", {"year": YEAR, "month": MONTH})
    results["mcp_fetch_settlement_recon_details"] = ok(r)

    section("A3c. create_instant_settlement (MCP) - expected RESTRICTED on hosted server")
    r = mcp_tool("create_instant_settlement", {"amount": 10000, "settle_full_balance": False,
                                               "description": "spike test instant settlement"})
    results["mcp_create_instant_settlement"] = ok(r)

section("A4a. Direct REST fallback")
r = http("GET", f"{API}/settlements?count=100", auth=AUTH, tag="rest_settlements_all")
results["rest_settlements"] = ok(r)

r = http("GET", f"{API}/settlements/recon/combined?year={YEAR}&month={MONTH:02d}",
         auth=AUTH, tag="rest_recon_combined_current_month")
results["rest_recon_current"] = ok(r)
if ok(r):
    b = body_of(r)
    print(f"  recon rows for {YEAR}-{MONTH:02d}: {b.get('count') if isinstance(b, dict) else '?'}")

# sweep the trailing 6 months - test accounts may have data in an earlier window
section("A4a-bis. Recon sweep, trailing 6 months")
sweep = {}
for i in range(6):
    d = (NOW.replace(day=1) - datetime.timedelta(days=1 if i else 0))
    y, m = NOW.year, NOW.month - i
    while m <= 0:
        m += 12; y -= 1
    rr = http("GET", f"{API}/settlements/recon/combined?year={y}&month={m:02d}",
              auth=AUTH, tag=f"rest_recon_{y}_{m:02d}")
    cnt = body_of(rr).get("count") if ok(rr) and isinstance(body_of(rr), dict) else None
    sweep[f"{y}-{m:02d}"] = cnt
    print(f"  {y}-{m:02d}: count={cnt}")
results["recon_sweep"] = sweep

section("A. Balance + instant-settlement eligibility (REST)")
http("GET", f"{API}/balance", auth=AUTH, tag="rest_balance")
http("GET", f"{API}/settlements/ondemand?count=100", auth=AUTH, tag="rest_ondemand_all")

section("VERDICT INPUTS")
print(json.dumps(results, indent=2))
(RAW.parent / "part_a_results.json").write_text(json.dumps(results, indent=2))
print(f"\nAll raw evidence in {RAW}")
