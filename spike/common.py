import base64, json, os, pathlib, time, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)

def load_env():
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    kid = os.environ.get("RAZORPAY_KEY_ID", "")
    sec = os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not kid or not sec:
        raise SystemExit("FATAL: set RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET (copy .env.example -> .env)")
    if not kid.startswith("rzp_test_"):
        raise SystemExit(f"FATAL: refusing to run — key id {kid[:12]}... is not rzp_test_*. LIVE KEYS ARE FORBIDDEN IN THIS SPIKE.")
    return kid, sec

def basic(kid, sec):
    return "Basic " + base64.b64encode(f"{kid}:{sec}".encode()).decode()

import random
_seq = [0]
RUNID = f"{int(time.time())%100000:05d}"

def log_raw(tag, req, status, headers, body):
    """Persist every raw request/response pair verbatim. This is the evidence trail."""
    _seq[0] += 1
    rec = {
        "seq": _seq[0], "tag": tag, "ts": int(time.time()),
        "request": req,
        "response": {"http_status": status, "headers": dict(headers or {}), "body": body},
    }
    p = RAW / f"{RUNID}_{_seq[0]:03d}_{tag}.json"
    p.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    print(f"  -> HTTP {status}  raw: {p.relative_to(ROOT.parent)}")
    return rec

def http(method, url, auth=None, body=None, extra_headers=None, tag="call"):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    headers.update(extra_headers or {})
    data = None
    if body is not None:
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    # redact auth in the evidence file
    safe_headers = {k: ("Basic <redacted>" if k.lower() == "authorization" else v) for k, v in headers.items()}
    reqrec = {"method": method, "url": url, "headers": safe_headers,
              "body": json.loads(json.dumps(body)) if isinstance(body, (dict, list)) else body}
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode(errors="replace")
            return log_raw(tag, reqrec, r.status, r.headers, try_json(raw))
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        return log_raw(tag, reqrec, e.code, e.headers, try_json(raw))
    except Exception as e:
        return log_raw(tag, reqrec, "TRANSPORT_ERROR", {}, repr(e))

def try_json(s):
    try:
        return json.loads(s)
    except Exception:
        return s

def body_of(rec):
    return rec["response"]["body"]

def ok(rec):
    return isinstance(rec["response"]["http_status"], int) and 200 <= rec["response"]["http_status"] < 300
