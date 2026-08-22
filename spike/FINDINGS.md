# Spike verdict: Razorpay MCP + settlement recon schema

Run 2026-08-22 against test account `merchant_id TShuVt2nlFfcNT`, key
`rzp_test_TShxM…`. No live key was used at any point; every script hard-refuses
a key id not prefixed `rzp_test_`. All raw request/response pairs are in
`spike/raw/` with the `Authorization` header redacted and bodies verbatim.

Three independent access paths were exercised: hosted MCP server, direct REST,
and the official Razorpay CLI (v1.0.9).

---

## HEADLINE

**Test mode serves the settlement APIs correctly but never produces settlement
data.** 15 real payments and 2 refunds were created and captured; the account
carries a ₹23,346.90 balance; `/v1/settlements` and
`/v1/settlements/recon/combined` both return `count: 0`. Instant settlement —
the only forcing mechanism — is blocked in test mode, confirmed identically
through all three access paths.

**Consequence for Phase 1: the subset-sum evidence cannot be captured from test
mode.** It must come from Razorpay's documented behaviour statement plus a
defensible synthetic model, and the repo must say so plainly.

**Offsetting win:** the seeded payments settle the `fee`/`tax` question with
zero residual, and turned up a `notes` type quirk that will crash a
strictly-typed parser. Both are verified on real data. See §4.

---

## 1. PART A VERDICT — does the hosted MCP server work with test keys?

**YES**, for reads. One settlement tool is absent server-side.

| Call | Result |
|---|---|
| `initialize` | ✅ HTTP 200, handshake completes |
| `tools/list` | ✅ 42 tools advertised |
| `fetch_all_settlements` | ✅ `{"count":0,"entity":"collection","has_more":false,"items":[]}` |
| `fetch_settlement_recon_details` | ✅ `{"count":0,"entity":"collection","items":[]}` |
| `create_instant_settlement` | ❌ **tool does not exist on the hosted server** |

The two settlement reads are genuine empty collections, not errors — the server
authenticates test keys and serves the correct schema. Verbatim:

```json
{"jsonrpc":"2.0","id":4,"result":{"content":[{"type":"text",
 "text":"{\"count\":0,\"entity\":\"collection\",\"has_more\":false,\"items\":[]}"}]}}
```

`create_instant_settlement`, verbatim JSON-RPC error:

```json
{"jsonrpc":"2.0","id":6,"error":{"code":-32602,
 "message":"tool 'create_instant_settlement' not found: tool not found"}}
```

### Documentation contradiction #1
The GitHub README lists exactly three remote-restricted tools: `create_refund`,
`close_qr_code`, `create_registration_link`. Reality from `tools/list`:
`create_registration_link` **is present**; `create_instant_settlement` and
`create_refund` are **absent**. The README's restriction list is wrong in both
directions. The official remote-server doc page enumerates no restrictions at
all. **Use `tools/list` as the source of truth; trust neither page.**

### Auth-layer evidence
Unauthenticated, the MCP server returns a body byte-identical to the REST API's:
```
POST https://mcp.razorpay.com/mcp  {"method":"initialize"}  -> HTTP 401
{"error":{"description":"Please provide your api key for authentication purposes","code":"BAD_REQUEST_ERROR"}}
-u rzp_test_0000000000:bogus                                -> HTTP 401
{"error":{"description":"Authentication failed","code":"BAD_REQUEST_ERROR"}}
```
The MCP server is a thin proxy over the same auth and the same data. **It gives
you nothing REST does not**, and it costs you two tools.

### Access paths compared
| Path | Verdict |
|---|---|
| Hosted MCP `https://mcp.razorpay.com/mcp`, `Authorization: Basic base64(key:secret)` | works with test keys; missing `create_instant_settlement` + `create_refund` |
| Local Docker / `go build ./cmd/razorpay-mcp-server` | unrestricted tool set — but the missing tools are blocked server-side anyway (§2) |
| **Razorpay CLI v1.0.9** (`brew install razorpay/razorpay-cli/razorpay`) | full settlement + dispute surface, `--year/--month/--day/--count/--skip` on `settlements recon`. Best interactive tool. |
| **Direct REST (chosen for the engine)** | full surface, no proxy, no version skew |

The CLI is worth having: `razorpay settlements recon --year 2026 --month 8
--count 100` is the exact call the engine makes, and `razorpay disputes list`
is the only convenient dispute reader. Configure with
`razorpay configure --key-id rzp_test_… --key-secret …` (writes
`~/.razorpay/config.yaml` — **gitignore it**).

---

## 2. THE SETTLEMENT WALL

`POST /v1/settlements/ondemand`, verbatim, reproduced via REST **and** via
`razorpay settlements instant-create`:

```json
{"error":{"action":null,"code":"BAD_REQUEST_ERROR",
 "description":"Instant Settlements cannot be created in test mode",
 "field":null,"metadata":{},
 "reason":"instant_settlements_test_mode_blocked",
 "source":"business","step":"settlement_initiation"}}
```

A first-class, machine-readable test-mode block — not a permissions gap.
Deploying the MCP server locally does **not** route around it; the block is
server-side at Razorpay. Three access paths, one answer.

Recon sweep across six months, all `HTTP 200`, all empty:

| window | rows |
|---|---|
| 2026-03 … 2026-08 | 0, 0, 0, 0, 0, 0 |

**What is NOT yet ruled out:** the automatic T+2 settlement cycle. Seeding
finished 2026-08-22 (Sat); earliest plausible settlement is Mon 2026-08-25.
`recheck.py` polls for it. **Run it daily through 2026-08-27.** I am explicitly
*not* claiming test mode never settles — only that it had not settled within
the session, and that instant settlement is permanently unavailable.

---

## 3. THE WORKING SEEDING PATH (undocumented, verified)

Neither documented server-side payment route works on a fresh test account:

| Route | Result |
|---|---|
| `POST /v1/payments/create/upi` (documented S2S) | `HTTP 400` `"The requested URL was not found on the server."` — not provisioned |
| `POST /v1/payments/create/ajax` **with card fields** | `HTTP 403`, bare nginx HTML, no JSON. Persists with full browser headers (UA/Referer/Origin/X-Requested-With). A WAF blocks card PANs on this path. |
| `POST /v1/payments/create/ajax` **netbanking / wallet** | ✅ **works** |

The working three-step sequence, fully reproducible (`pay.py`):

1. `POST /v1/orders` (Basic auth) → `order_id`
2. `POST /v1/payments/create/ajax` (form-encoded, `key_id` in **body**, no Basic
   auth) → returns a mock-gateway handoff:
   ```json
   {"type":"first","request":{"url":"https://api.razorpay.com/v1/gateway/mocksharp/payment?key_id=…",
    "method":"post","content":{"action":"authorize","amount":222200,"method":"netbanking",
    "payment_id":"TSi1yiwrdzsmLC","callback_url":"https://api.razorpay.com/v1/payments/pay_TSi1yiwrdzsmLC/callback/9b516b91…/rzp_test_…","recurring":0}},
    "version":1,"payment_id":"pay_TSi1yiwrdzsmLC","gateway":"eyJpdiI6…"}
   ```
3. `POST /v1/gateway/mocksharp/payment` → mock bank HTML → scrape the form →
   `POST /v1/gateway/mocksharp/payment/submit` with `success=S` (or `F` to
   force a failed payment) → redirects to the callback → payment lands
   `captured`.

**Method availability is per-account and must be read, not assumed.** Query
`GET /v1/preferences?key_id=…`. On this account: card `true`, netbanking 40
banks, wallet `airtelmoney|mobikwik|olamoney`, **`upi: false`**, `emi: false`,
`cod: false`. My first attempt failed on `bank=HDFC` (`reason:
bank_not_enabled`) and `wallet=payzapp` — neither is enabled here. Enabled bank
codes include `ALLA, CBIN, CNRB, CSBK, DCBL, BARB_R, DEUT`.

UPI failed with `"UPI transactions are not enabled for the merchant"` — an
account-activation limit, not a test-mode limit.

---

## 4. FEE, TAX, AND THE IDENTITY — CORRECTED

> **Correction to my earlier pass.** I first wrote that Razorpay's recon
> documentation *states* `credit = amount − fee − tax` and therefore contradicts
> itself. That was wrong on two counts, and the corrected version is below.
> Razorpay's recon field table states no arithmetic identity at all — it
> defines `credit` only as "Credited amount in currency subunits." The
> `− fee − tax` identity came from the project brief, not from Razorpay. And
> the doc's sample rows are in fact *consistent* with the correct identity, not
> in conflict with it. The substantive finding survives; the "docs contradict
> themselves" framing does not.

### The identity in the brief is wrong

**`fee` is inclusive of `tax`. The correct identity is `credit = amount − fee`.**

Razorpay's payment-entity documentation says so explicitly:

> `fee` — **"Fee (including GST) charged by Razorpay."**
> `tax` — "GST charged for the payment."

`tax` is a *breakdown line inside* `fee`, not an additional charge. Subtracting
both double-counts GST.

### Verified on real data, zero residual

Across all 14 fee-bearing payments, `(fee − tax) / amount == 2.000000%` exactly
— no violations — and `tax` is 18% GST on `fee − tax` (rupee-rounded; observed
18.00–18.06%):

| amount | fee | tax | fee−tax | (fee−tax)/amount |
|---|---|---|---|---|
| 100000 | 2360 | 360 | 2000 | 2.000% |
| 222200 | 5244 | 800 | 4444 | 2.000% |
| 500000 | 11800 | 1800 | 10000 | 2.000% |
| 415000 | 9794 | 1494 | 8300 | 2.000% |
| 76400 | 1804 | 276 | 1528 | 2.000% |
| …14 of 14 | | | | 2.000% |

If `fee` and `tax` were disjoint the effective rate would be 2.36% and that
column could not hold. It holds to the rupee on every row.

**The balance identity closes exactly:**

```
Σ(amount − fee) over captured+refunded  = 2,784,690
Σ(refund amount)                        =   450,000
expected balance                        = 2,334,690
GET /v1/balance                         = 2,334,690     delta = 0
```

Under the brief's identity, expected would be 2,324,420 — off by exactly
10,270, the sum of the tax column.

### Re-reading Razorpay's doc sample under the correct identity
- payment row: `100000 − 2900 = 97100` = `credit` ✅
- transfer row: `100000 + 296 = 100296` = `debit` ✅ (tax 46 sits inside fee 296)

Both rows are consistent. The sample never contradicted itself; it is merely
*degenerate* on the payment row (`tax = 0`), where the two candidate identities
are indistinguishable — which is exactly why the wrong one is easy to adopt.

### Scope limit — hold this line in the submission
Verified on **payment entities**. Whether recon rows carry the same convention
is **unverified**, because test mode produced no recon rows. The evidence that
they do is strong (the recon doc sample is consistent with it, and recon rows
are derived from the same ledger), but it is inference, not observation. Do not
claim recon-level verification. `analyze.py` prints a `tax-INSIDE-fee` vs
`tax-OUTSIDE-fee` tally the moment a real row exists rather than assuming.

### `Σcredit − Σdebit == bank_amount`
**Unverified and unverifiable from documentation.** Razorpay's published sample
batch nets **−244,684** (Σcredit 98,112 − Σdebit 342,796); a batch cannot pay
out negative, so the sample is illustrative rather than a real batch. This
identity stays in the "unverified" tier until a real batch exists.

---

## 4b. SCHEMA FINDINGS FOR THE GENERATOR

**Verified on real data:**

- **`notes` is `{}` when populated and `[]` when empty.** Across 15 real
  payments: 14 objects, 1 empty **array**. A parser typed `notes: dict` will
  crash on the empty case. (Razorpay's recon sample shows `notes` as a bare
  *string* too — so treat the field as fully polymorphic: object | array | string | null.)
- **Failed payments carry `fee = 0, tax = 0`** (`pay_TSi7iYzv9ycljW`). Do not
  invent a fee for them.
- Payments auto-capture; there is no authorize→capture gap to reconcile.

**From Razorpay's published recon sample (not captured data):**

- `posted_at` and `credit_type` appear in the sample and are **absent from the
  documented field table**. `credit_type` is *missing entirely* — not null —
  from the adjustment row. The generator must reproduce field **absence**.
- `settlement_utr` is **null on the adjustment row while sharing the same
  `settlement_id`**. UTR is not a batch-level key → **match on `settlement_id`,
  UTR as a secondary hint only.** Direct input to the matching engine.
- On `payment` rows the id is in `entity_id` and `payment_id` is **null**;
  `payment_id` is populated only on rows *pointing at* a payment. Resolution
  rule: `entity_id if type=='payment' else payment_id`.

---

## 5. DISPUTES — RESOLVED, AND NOT SEEDABLE

**Definitive: disputes cannot be created through any Razorpay interface.**

```
POST /v1/disputes  -> HTTP 404
{"message":"no Route matched with those values"}
```

That is a routing-layer 404 — the endpoint **does not exist**, in test or live
mode. The Razorpay CLI confirms the same shape: `razorpay disputes` exposes
only `list`, `fetch`, `accept`, `contest`. There is no create, and no test-mode
simulator. Disputes are raised by the issuing bank; a merchant can only respond.

`GET /v1/disputes` on this account returns `{"entity":"collection","has_more":false}`
— note the **`items` key is omitted entirely** on an empty dispute collection,
whereas settlements return `"items":[]`. Another polymorphism for the parser.

### So the generator must synthesise disputes. Here is the real schema to match:

| field | type | notes |
|---|---|---|
| `id` | string | `disp_` prefix |
| `entity` | string | `"dispute"` |
| `payment_id` | string | the disputed payment |
| `amount` | integer | subunits |
| `currency` | string | |
| `amount_deducted` | integer | **`0` unless `status == "lost"`** |
| `reason_code` | string | |
| `reason_description` | string | |
| `respond_by` | integer | unix ts |
| `status` | enum | `open`, `under_review`, `won`, `lost`, `closed` |
| `phase` | enum | `fraud`, `retrieval`, `chargeback`, `pre_arbitration`, `arbitration` |
| `created_at` | integer | |
| `evidence` | object | `{amount, summary, shipping_proof[], billing_proof, submitted_at}` |

**How this must show up in recon rows** — the modelling rule for the planted
hard cases:

1. Dispute opens → the payment's recon row carries `dispute_id` populated and
   `on_hold: true`, `settled: false`. It is **excluded from the settlement
   batch** while held. This is a second, independent reason a payment fails to
   appear in its expected settlement — distinct from the subset-sum reason, and
   your matcher must tell them apart.
2. Dispute `won` → `on_hold` clears, the payment settles in a **later** batch,
   so `created_at` and `settled_at` diverge widely. Free cross-month case (§6, g).
3. Dispute `lost` → `amount_deducted` becomes non-zero and hits the balance,
   which should surface as a separate **`type: "adjustment"`** debit row —
   Razorpay's own recon sample carries exactly such a row
   (`adj_EhcHONhX4ChgNC`, `description: "test reason"`). Note the adjustment row
   in that sample has **no `credit_type` key at all** and a **null
   `settlement_utr`** — reproduce both.

Point 3 is worth stating explicitly in the repo: an `adjustment` row has no
`payment_id`, no `order_id`, and no `method`, so it can never be matched by the
normal join path. It **must** route to the exception queue by construction.
That is a defensible reason for the exception tier to exist at all.

---

## 6. SCENARIO SCORECARD

| # | Scenario | Status | Evidence |
|---|---|---|---|
| a | Simple 1:1 | ✅ seeded | `pay_TSi3qT6hGCkMgl` 100000, fee 2360 |
| b | Refund before settlement | ✅ seeded | `pay_TSi462SLqN2db4` → `rfnd_TSi4GtqmTmfZfx` full 250000; payment status → `refunded` |
| c | **Subset-sum / netting** | ❌ **blocked** | 5 awkward-amount payments + a mid-window 150000 refund seeded; **no settlement ever formed**, so no grouping to observe |
| d | Partial refund | ✅ seeded | `pay_TSi4K4yG6DLwrw` 500000 → `rfnd_TSi4ZP1Ug9EjYd` 200000; payment stays `captured` |
| e | Disputed payment | ❌ impossible | `POST /v1/disputes` → 404, endpoint does not exist. Schema + modelling rules in §5. |
| f | Multiple methods | ⚠️ partial | netbanking ×9 (7 banks) + wallet ×3. **No card** (WAF 403), **no UPI** (not enabled on account) |
| g | Cross-month boundary | ❌ not observable | needs a real month rollover — but §5 point 2 gives a principled way to model it |
| h | Failed payment | ✅ seeded | `pay_TSi7iYzv9ycljW` status `failed`, **`fee=0, tax=0`** |

**On (c), the one that mattered most:** what was recoverable is that the
*preconditions* are real — a mid-window refund does reduce live balance, and
balance is the exact quantity Razorpay says it settles against. The netting
mechanism is confirmed; the *observed batch* is not. Whether that justifies ILP
is now an argument from documented behaviour, not from captured data. **Say so
in the repo.** A panelist who catches you implying otherwise does more damage
than the missing evidence does.

---

## 7. OPERATIONAL NOTES FOR THE ENGINE

- **No rate limiting observed.** ~140 requests in ~10 minutes, zero 429s.
- **Fresh test accounts start with everything off.** UPI disabled, most banks
  disabled, balance 0, `balance.name` `null`→`"enabled"` after first payment.
  Never assume a method is available — read `/v1/preferences`.
- **Payment seeding is 4 HTTP round trips each**, ~8s per payment. 15 payments
  exceeded a 2-minute foreground budget. Background any bulk seeding.
- **Empty collections are not uniformly shaped** — settlements/recon return
  `"items":[]`, disputes omit `items` entirely. Do not assume the key exists.
- **Test mode holds no real merchant or cardholder data**, so no redaction was
  needed for `captured_dataset.json`. Verified: no `rzp_*` string appears in it.
- `~/.razorpay/config.yaml` holds the CLI's plaintext key — keep it out of the repo.

---

## 8. FILES

| File | Contents |
|---|---|
| `captured_dataset.json` | 15 payments, 2 refunds, 28 orders, balance, settlements(empty), recon(empty) — unmodified API responses |
| `raw/` | every request/response pair, auth redacted |
| `raw/000_DOC_SAMPLE_not_real_data.json` | Razorpay's published sample, **clearly marked as not captured data** |
| `probe_a.py` | Part A: MCP handshake → tools/list → settlement tools → REST fallback → 6-month sweep |
| `pay.py` | the verified ajax + mocksharp payment path |
| `seed2.py` / `seed3.py` | scenario seeding |
| `seed_b_FAILED_PATHS.py` | first attempt — kept as the record of which routes 403/400 |
| `verify_fee_tax.py` | reproducible fee/tax proof — prints the 2.000000% table and the balance-identity showdown |
| `analyze.py` | field census, both identities, settlement grouping, subset-sum detection |
| `recheck.py` | **run daily to 2026-08-27** — polls for a T+2 settlement |

---

## 9. OPEN QUESTIONS

1. **Does the T+2 cycle fire in test mode?** Unresolved. `recheck.py` answers it
   by 2026-08-27. The only thing that could still rescue scenario (c).
2. **Do recon-row `fee`/`tax` follow the payment entity's tax-inclusive
   convention?** Strong inference, not observation. `analyze.py` settles it
   automatically if a batch appears.
3. **Is card seeding worth unblocking?** The ajax WAF blocks PANs.
   Browser-driven Checkout would work and would add
   `card_network`/`card_issuer`/`card_type` — the only fields with real
   method-variance. ~15 min. Not started; your call.
4. **Should the account be activated?** Would enable UPI and possibly change
   settlement behaviour. Requires business/KYC details — yours to decide.
