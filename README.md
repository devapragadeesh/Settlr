# Razorpay AI Buildathon — Council Conclusion

**Decision: Track 04 — AI Finance Controller. Build the "Settlement Truth Engine."**

A research council of six agents investigated the event, Razorpay's real product surface, and all five tracks. Every claim about an existing Razorpay feature below was then **verified against primary sources** (Razorpay docs, product pages, official GitHub). Verification status is marked throughout.

---

## 1. What this event actually is

Not a weekend team hackathon. It is a **student-only hiring funnel** for an "AI Builder Intern" role.

| | |
|---|---|
| Role | AI Builder Intern — ₹75,000/month, 6 or 12 months |
| Location | Bangalore, in-person, from September |
| Eligibility | Enrolled students, graduating 2027–2029 |
| Registration | Reported 5 September 2026 *(third-party sources only — not on the official page)* |
| Process | Pick track → build → **public GitHub repo** → **5-min recorded video** → architecture walkthrough → panel interview |
| Not included | No resume screen, no aptitude test, no group discussion |

**Three consequences that drive everything else:**

1. **The pitch is recorded, not live.** Demo craft is a production problem, not a nerves problem. There is no excuse for an unrehearsed failure moment.
2. **You are cross-examined.** The architecture walkthrough plus panel interview means the repo must survive *"why did you choose this?"* from Razorpay engineers. Defensibility beats polish.
3. **Downside risk dominates.** In a hackathon a broken demo costs a prize. Here one unjustifiable decision costs the offer.

⚠️ **The application form is a 5-field lead capture** (email, name, college, grad year, September availability). It does **not** collect a repo or a track. So the build is gated later in the funnel — the September date is likely *registration*, not *submission*. **Confirm before compressing scope.**

---

## 2. The verification pass — what Razorpay already ships

This is the single most important input, because building something Razorpay already sells means demoing a competitor's product to its own team.

### ✅ VERIFIED — Razorpay Agent Studio exists, and ships 7 agents

Source: `razorpay.com/agent-studio/`. **All seven are early access, not GA.**

| Agent | What it does |
|---|---|
| Dispute Responder | Auto-responds to chargebacks with optimised evidence |
| Subscription Recovery | Analyses failed subscription payments, smarter retries, nudges |
| Abandoned Cart Conversion | Re-engages via WhatsApp/email with personalised offers |
| RTO Shield | Detects high-risk COD orders using LLM address validation |
| RTO Insights | Analyses RTO patterns across pincodes, products, customers |
| Settlement Insights | **Sends a daily settlement summary via WhatsApp** |
| Cashflow Forecaster | Predicts cash position 3–7 days ahead |

**Treat this as a "do not build" list.** It covers the obvious idea in Tracks 01, 02 and 03.

**But note the two finance agents are shallow.** "Settlement Insights" is a *WhatsApp summary*. "Cashflow Forecaster" is a *3–7 day notifier*. Neither reconciles anything. This is the gap.

### ✅ VERIFIED — the subset-sum settlement behaviour (the key technical finding)

Razorpay's settlement docs state **verbatim**:

> "when settling transactions, we will only choose the ones that add up to your current live balance"

With a worked example: three payments totalling ₹1000, a ₹100 refund drops live balance to ₹900, so only the payments summing to ₹900 settle — the rest rolls to the next slot.

**This is the entire justification for the constraint solver.** A settlement batch is a *subset-sum* of eligible payments, not "everything from T-2." Naive 1:1 matching cannot represent this. Primary-source confirmed.

### ✅ VERIFIED — the recon API schema

`GET /v1/settlements/recon/combined?year=yyyy&month=mm` returns:

```
entity_id, type, debit, credit, amount, currency, fee, tax, on_hold, settled,
created_at, settled_at, settlement_id, description, notes, payment_id,
settlement_utr, order_id, order_receipt, method, card_network, card_issuer,
card_type, dispute_id
```

Amounts in **paise**. Sample confirms `amount 100000, fee 2900, tax 0, credit 97100`.

### ✅ VERIFIED — Optimizer Single View Recon does NOT close the loop

It consolidates multi-gateway payments and settlements into one dashboard: status, UTR, settlement IDs, gateway fees, settlement↔payment mapping. Claims 20–40 hours/month saved.

**It explicitly does not cover: GST/tax lines, ERP matching, accounting-software connectivity, or automated bank-statement matching.** Its one stated limitation is late authorisations. This directly confirms the white space.

### ✅ VERIFIED — Razorpay MCP server, 47 tools, includes recon

Includes `fetch_settlement_recon_details`, `fetch_all_settlements`, `create_instant_settlement`, plus `detect_stack` and `integrate_razorpay_checkout` codegen helpers. **Test-mode support is not documented — verify with a test key on day one.**

### ✅ VERIFIED — Thirdwatch merged into Magic Checkout, and publishes no model metrics

Confirmed verbatim: "Thirdwatch offerings have been merged with Razorpay Magic Checkout." Features include auto-disabling COD on risky orders and ML RTO probability.

**No precision, recall, accuracy or false-positive metrics are published anywhere.** Only business outcomes: "40% more conversions" and "30% lesser RTOs." That gap is real — but see Track 02 below for why exploiting it is harder than it looks.

### ✅ VERIFIED — Intelligent Retry Engine exists (beta)

Configurable retry cadence and templates, smart retries timed on user context and bank availability, WhatsApp recovery links, smart routing on latency/downtime. **Introduced in beta at FTX 2026.** This occupies most of Track 03's mandate-retry space.

### ⚠️ UNVERIFIED — treat with caution

- **"Razorpay Recon" metrics** (200M txns/month, 80% productivity). The blog post is pure marketing: no sources named, no metrics, no scope. Does not specify what it connects to. **Do not cite.**
- **Vulcan payments foundation model** — announced via press release, not independently confirmed here.
- Bank narration templates and UTR formats — vendor blogs only. Design input, not stage claims.
- The Sec 194-O → Sec 393(1) renumbering under the Income Tax Act 2025 — practitioner blogs only. Verify against the bare act before stating publicly.

---

## 3. Every track, in simple words

### Track 01 — AI Growth & Agentic Commerce

**Why:** It's the frontier problem, and Razorpay is genuinely invested — live NPCI pilots, an official MCP server, partnerships with Anthropic and OpenAI. Their internals researcher ranked merchant-side agentic infrastructure as the **#1 white space** in the whole company. Highest ceiling on the board.

**Why not:** It's the hype track, so most applicants will pick it. Razorpay's own MCP server makes the happy path *too* easy — hundreds of people will wire the same tool calls and ship the same conversational checkout. You'd compete directly against Agent Studio, built by the people interviewing you. And NPCI's UAP is still **pre-spec** — no published circular, no sandbox, no RBI approval — so your central claim is about a future you can't demonstrate.

**Verdict:** Best idea in the track (a mandate broker bridging ACP/UCP checkout to UPI Reserve Pay) is genuinely unbuilt. But high variance, and you're arguing about the future instead of showing a working present.

### Track 02 — AI Risk Manager

**Why:** Least crowded. Razorpay *themselves* wrote that this track "surfaces the risk and ML minded builders the others miss" — that is the organisers admitting they under-recruit here. And they publish no model metrics at all, so a cost-calibrated decision layer is genuinely additive.

**Why not:** **There is no public Indian RTO dataset.** So you generate your own — and in fraud detection, ground truth *is your own generative choice*. You plant the fraud, then detect it. That's circular: you're measuring how well your model learned your simulator, and a sharp judge kills it in one question. You'd also be building next to Thirdwatch, RTO Shield *and* Vulcan.

**Verdict:** Real opportunity, permanently capped by the data problem.

### Track 03 — AI Revenue Recovery

**Why:** Big, real, quantified pain. UPI Autopay fails at 8–15% vs 2–3% for card mandates. A legally compliant retry sequencer is a genuinely interesting *constrained optimisation* problem — NPCI allows max 1 original + 3 retries per mandate sequence, non-peak hours only, with 24h pre-debit notice.

**Why not:** Agent Studio ships Subscription Recovery *and* Abandoned Cart Conversion, and the Intelligent Retry Engine is in beta. Most of this track is already product. Checkout drop-off recovery is the single most saturated direction in the entire event.

**Verdict:** One live corner remains — **B2B receivables**, which Agent Studio doesn't touch, with a sharp hook: Section 43B(h) means overdue MSME payables are disallowed as a tax deduction until paid, so an agent can quantify the *buyer's tax exposure* as leverage. Strong, but narrower than it first appears.

### Track 04 — AI Finance Controller ⭐

**Why:** Least crowded — reconciliation is invisible to students and unglamorous. The bar (50+ records, match rate, honest exception list) is **bounded, gradeable, and closed-form** — the only track where you can be *certain* you cleared it, because you control the data. The evidence *is* the product: the exception list is your graceful-failure moment, for free. And Razorpay's own framing for this track — *"verification capacity, not generation speed, is the bottleneck"* — means you'd be building a verification system for a company that just said verification is their bottleneck.

Crucially, **synthetic data is legitimate here in a way it isn't for fraud.** Ground truth is an *arithmetic identity* (`credit = amount − fee − tax`, and `Σcredit − Σdebit == bank_amount`). The answer key is derivable and independently checkable. A judge can verify your matcher without trusting your generator. That asymmetry is the deciding argument.

**Why not:** Not virgin territory — Razorpay Recon exists (though its marketing is unverifiable) and Optimizer has Single View Recon. Lower ceiling than Track 01: it will not make anyone gasp. You must resist the phrase "AI reconciliation," which is crowded globally (Basis, Numeric, Ramp, HighRadius).

**Verdict:** Highest floor. The wedge is specific and verified — the constraint solver plus the India tax leg plus evidence-backed exception *resolution*, none of which Single View Recon covers.

### Track 05 — Open Track

**Why:** Freedom to build the thing you understand best.

**Why not:** "Open doesn't mean easier" — same bar, but you also carry the burden of proving the problem is real, with none of the scaffolding a track gives you. Likely to attract pet projects, so the shallow end is crowded even if the deep end isn't. For a hiring funnel where alignment with the company matters, choosing a track signals you engaged with their actual business.

**Verdict:** Only worth it with a problem you have unfair personal insight into.

---

## 4. The build: Settlement Truth Engine

Closes one loop end to end: **PG payments → settlement batches → bank credits → ERP orders → GST/tax lines**, for one month.

### Architecture — a 4-stage cascade

| Stage | Method | Target |
|---|---|---|
| 1. Exact join | `payment_id` / `order_id` / `settlement_id` / UTR | ~75% |
| 2. Fuzzy blocking | ±3d window, ±₹1 or 0.5% tolerance, rapidfuzz on narration | ~88% cumulative |
| 3. **Constraint solver** | Hungarian for 1:1; **ILP/subset-sum** for netting | ~94–97% cumulative |
| 4. Exception routing | LLM emits `{type, evidence, proposed_JE, confidence, owner}` | 3–6% honest residual |

**The governing rule: LLM-as-explainer and LLM-as-router — never LLM-as-matcher.** Matching is arithmetic. A model asked to match rows hallucinates, is non-deterministic across runs, and cannot show a proof. Stage 3 is the differentiator: `Σcredit − Σdebit over rows assigned to batch X == bank_amount(UTR) ± tolerance`.

### What can actually be implemented today

Everything below is confirmed available:

- ✅ **Recon data in the exact production schema** — via `fetch_settlement_recon_details` on the official MCP server, or `GET /v1/settlements/recon/combined` directly
- ✅ **Test-mode orders, payments, refunds, settlements** — all callable with `rzp_test_*` keys
- ✅ **The solver** — `scipy.optimize.linear_sum_assignment` for 1:1; PuLP or OR-Tools for subset-sum netting. Pure Python, no infrastructure
- ✅ **Synthetic generator** — 240 rows / 12 batches, seeded and reproducible, emitting the verified schema with 15 classes of planted hard cases and a hidden ground-truth key
- ⚠️ **MCP test-mode support is undocumented** — validate on day one; fall back to the local Docker MCP or direct REST if the hosted server rejects test keys

### The metrics line

```
Records: 240 | Auto-matched: 229 (95.4%) | Precision on auto-matches: 100% (0 false matches)
Exceptions: 11 (4.6%), fully itemized with cause | Value recovered: ₹X fee overcharge + ₹Y unclaimed ITC
Runtime: Ns | Deterministic: identical output across 3 runs
```

Report **precision alongside recall** — a matcher that matches everything scores 100% recall and is worthless. Showing you know that *is* the bar. Claim ~95% with an honest exception list; a claimed 100% reads as a bug or a lie.

---

## 5. The council — 8 agents in `.claude/agents/`

| Agent | Owns |
|---|---|
| `recon-architect` | Decisions **with rejected alternatives**; guards the cascade |
| `synthetic-data-forge` | The dataset, 14 hard-case classes, hidden ground truth |
| `matching-engine` | The 4-stage cascade and the ILP solver |
| `eval-harness` | Precision *alongside* recall, held-out discipline, determinism |
| `compliance-counsel` | Tiers every tax claim: verified / secondary / do-not-state |
| `repo-craftsman` | README, `AGENTS.md`, tests, CI |
| `pitch-director` | The 4:45 video, failure moment at ~3:30 |
| `red-team-panelist` | Adversarial mock panel; would-hire / would-not-hire |

Four of eight exist purely to keep you honest. That weighting is deliberate: every track's bar asks the same thing in five dialects — **evidence that you know how to know whether your system works.**

`repo-craftsman` is built against Razorpay's own published "Slash" engineering standard: **Context, Testing, CI/CD**, scoped auditable permissions, measured metrics. They published their own answer key.

---

## 6. Anti-patterns that lose this format

1. **Breadth as insurance** — four half-loops instead of one closed loop. A closed loop is checkable; breadth isn't.
2. **Cherry-picked results** — the track bar names this explicitly.
3. **Evaluating on data you tuned against** — trivially exposed in Q&A.
4. **Hiding the exception list** — it's the asset. Suppressing it reads as dishonesty or blindness.
5. **Framework-shaped answers** — "I used LangGraph" is not a reason. Have a rejected-alternatives paragraph.
6. **Unbounded agent authority** — contradicts their own published standard.
7. **A repo the reviewer can't run** — friction converts to rejection.
8. **Repo/video mismatch** — the most damaging thing a panel can discover.

---

## 7. Switch condition

Revisit this decision **if NPCI publishes the UAP spec or opens a sandbox before you start building.** That converts the Track 01 mandate broker from visionary-maybe to verifiable-now, and it becomes the better project outright. Worth one check.
