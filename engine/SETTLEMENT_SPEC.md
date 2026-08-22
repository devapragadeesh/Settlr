# SETTLEMENT_SPEC.md — the settlement batching rule this simulator implements

**Status:** normative. `simulator.py` implements this document and nothing else.
**Provenance:** every rule below is tagged with the tier it is sourced at.

| tier | meaning |
|---|---|
| `captured_real` | observed in this project's own Razorpay test-account capture (`spike/captured_dataset.json`) |
| `synthesized_documented` | grounded in a citable Razorpay statement, quoted verbatim with its URL |
| `synthesized_modelled` | statute or standard industry practice; **no Razorpay source** |

---

## 0. Why a simulator exists at all

Razorpay test mode serves the settlement APIs correctly but **never produces
settlement data**. 15 payments and 2 refunds were captured on account
`merchant_id TShuVt2nlFfcNT`; the account carried a ₹23,346.90 balance;
`/v1/settlements` and `/v1/settlements/recon/combined` both returned `count: 0`
for every month probed. The only forcing mechanism, instant settlement, is
blocked server-side with a first-class machine-readable reason code:

```json
{"error":{"code":"BAD_REQUEST_ERROR",
 "description":"Instant Settlements cannot be created in test mode",
 "reason":"instant_settlements_test_mode_blocked",
 "source":"business","step":"settlement_initiation"}}
```

Reproduced identically via REST, the hosted MCP server, and the Razorpay CLI
v1.0.9. A locally built MCP server does not route around it — the block is
server-side at Razorpay.

**Therefore settlement batching in this dataset is synthesized from Razorpay's
documented behaviour, not captured.** No row in the emitted dataset claims
otherwise; see the `source_tier` field on every row.

---

## 1. The batching rule — primary source

Source: <https://razorpay.com/docs/payments/settlements/> — tier
`synthesized_documented`.

> "When settling transactions, we will only choose the ones that add up to your
> current live balance."

and the settlement cycle:

> "The standard settlement cycle for domestic payments is **T+2** working days
> (where **T** is the date of transaction capture)."

and the worked example, verbatim:

> "You captured three payments of P1 - ₹500, P2 - ₹300 and P3 - ₹200 on July 02,
> 2023, and your settlement schedule is T+2 days 5:00 p.m. Hence, the live
> balance is ₹1000, which will be the settlement amount. However, on July 02,
> 2023, you had to refund your customer ₹100. Due to this, your live balance is
> ₹900. As the current live balance is lesser than the settlement scheduled,
> Razorpay will initiate partial settlements and settle transactions P1 and P2
> on T+2 as it adds upto ₹900."

### 1.1 The worked example admits more than one reading

P1 + P2 = ₹800, not ₹900. No subset of {500, 300, 200} sums to 900. The prose
"as it adds upto ₹900" does not disambiguate what the batch actually is, and
the example is consistent with several different mechanisms. **This spec does
not claim the documentation is wrong.** It enumerates the readings it can see,
commits to one, and names the rest so the choice is auditable.

| reading | rule | reproduces the stated selection {P1, P2}? | closes at ₹900? |
|---|---|:-:|:-:|
| **(A) exact equality** | pick S with `Σcredit(S) == live_balance` | ✗ — no subset equals 900, so the rule is unsatisfiable and the batch is empty | ✗ |
| **(B) maximal subset under a cap** | maximise `Σcredit(S)` s.t. `Σcredit(S) ≤ live_balance` | ✓ — {P1,P2}=800 is the largest feasible | ✗ (800) |
| **(C) refund consumes one payment** | the ₹100 refund is applied against P3, which is dropped whole; P3's residual ₹100 rolls | ✓ | ✗ (800) |
| **(D) debits net inside the batch** | settle *all* eligible payments; the refund is a `debit` row in the same batch, so payout = 1000 − 100 | partial — all three settle, but the doc names only P1 and P2 | ✓ (900) |
| **(E) FIFO under a cap** | take eligible payments in capture order until the next would breach live balance | ✓ — 500, then 300; 200 would breach | ✗ (800) |

**No reading reproduces both the stated selection and the stated arithmetic.**
(B), (C) and (E) reproduce the selection; (D) reproduces the arithmetic. That
is the honest summary, and it is a stronger statement than "the docs are
broken."

**This spec implements (B), with (E) available as a one-line swap.**

Why (B) over the others:

- over (A): (A) makes Razorpay's own example unsatisfiable.
- over (C): (C) requires knowing which payment a refund was raised against, and
  privileges that payment in a way nothing in the documentation supports.
- over (D): (D) is genuinely well supported — §3 of this spec cites Razorpay's
  published recon sample, in which a refund *is* a `debit` row sharing a
  `settlement_id` with payment rows, and this spec adopts that structure. But
  under (D) the selection rule does no work at all, every eligible payment
  always settles, and the doc's "settle transactions P1 and P2" is simply not
  describing the batch. (D) is retained in the model as the *row structure*;
  it is rejected as the *selection rule*.
- over (E): (E) is very likely closer to what the production service does — a
  settlement service does not run an exponential optimiser per merchant per
  day — but it can never be ambiguous, and the ambiguity of the documented rule
  is a real property worth exposing (§2).

**The reading is a parameter, not a buried assumption.**
`SimulatorConfig.selection_rule` takes `"max_under_cap"` or `"fifo_under_cap"`,
and the frozen ground-truth key records which one produced the data
(`selection_rule`). If the production service turns out to settle FIFO-under-cap,
the same ledger regenerates into a different dataset without touching the
reconciliation engine, because **the reconciliation problem is identical under
either reading**: a bank credit and a set of candidate rows. The reading changes
the data, not the engine.

### 1.2 The rule, formally

At each batch formation time `t`:

```
release_holds(t)                       # disputes resolved on/before t

E(t)  = { p : p.captured
              and eligible_at(p) <= t
              and not on_hold(p, t)
              and not settled(p)
              and not netted_out(p) }              # eligible credits

D(t)  = { d : d.created_at <= t and not settled(d) }   # pending debits
                                                       # (refunds, adjustments)

available(t) = Σ credit(p) for every unsettled, captured, not-on-hold payment
                                        # ALL ages, not just eligible ones
             − Σ debit(d) for d in D(t)
                                        # this is `live balance`

S(t)  = argmax  Σ credit(S)   over S ⊆ E(t)
        subject to Σ credit(S) ≤ available(t)

payout(t) = Σ credit(S(t)) − Σ debit(D(t))
```

`E(t) \ S(t)` rolls forward to `t+1` unchanged. `payout(t)` is the single credit
that appears on the merchant's bank statement.

### 1.3 Held funds are excluded from live balance

`GET /v1/balance` returns a `locked_balance` field (observed `0` on the captured
account — tier `captured_real` for the field's existence, `synthesized_modelled`
for the semantics). Payments under dispute hold are treated as locked: their
credit is excluded from `available(t)` and they are not in `E(t)`.

### 1.4 Non-negative payout

If `payout(t) < 0` the batch cannot pay out. Debits are deferred to the next
batch, largest first, until `payout(t) >= 0`. If no non-negative payout is
reachable the batch is skipped entirely. Tier `synthesized_modelled` — Razorpay
documents no behaviour for a negative-balance batch.

---

### 1.5 Where exact enumeration stops being the right algorithm

`S(t)` is solved exactly by meet-in-the-middle, which is exponential in
`|E(t)|`. That is tractable for the pool sizes in this dataset (see
`pool_size` on every batch in the ground-truth key) and **is not tractable at
merchant scale**, where a batch can contain thousands of eligible payments.

Above `SimulatorConfig.max_pool` the simulator **degrades to the FIFO reading
(E) and records the degradation** on the batch as `selection_degraded: true`,
rather than raising. Raising would pretend the case does not arise; silently
degrading would misrepresent which batches were solved exactly. Both are worse
than saying so.

This is a stated boundary, not a solved problem. A production engine would not
enumerate; it would exploit the fact that the rule is *checkable* in linear time
even where it is expensive to *invert*.

Note `available(t)` counts credits from payments that are **not yet T+2 eligible**.
Money captured yesterday is in the live balance even though it cannot settle
today. This is what makes the constraint bind only when debits are material —
exactly the situation the Razorpay example describes.

## 2. Ambiguity is a first-class outcome

Reading (B) has no tie-break. When two or more distinct subsets both achieve the
maximum feasible sum, **the bank credit alone does not identify which payments
settled.** This is not a modelling weakness — it is a provable property of the
documented rule, and it is the reason the reconciliation engine must be able to
return "ambiguous" rather than a confident wrong answer.

The simulator:

1. enumerates **all** subsets achieving the maximum (meet-in-the-middle, exact);
   if more than `tie_limit` (64) subsets tie, enumeration stops and the batch is
   marked `tying_decompositions_truncated: true` — such a batch is *more*
   ambiguous, not less, and the register is then explicitly a sample rather
   than silently a partial list presented as complete;
2. if `|maximal subsets| > 1`, records the batch as `ambiguous: true` in the
   ground-truth key together with **every** tying decomposition;
3. picks one deterministically for the emitted data — the subset whose sorted
   tuple of entity ids is lexicographically smallest.

The emitted dataset carries **no marker** of which batches are ambiguous. A
solver that returns a single confident decomposition for an ambiguous batch is
wrong even when it happens to pick the same subset the simulator did, because it
cannot have known. `tests/test_ambiguity.py` encodes that contract.

---

## 3. Eligibility and the refund lifecycle

`eligible_at(p) = p.created_at + 2 working days`, at the batch cut-off time.
Working days exclude Saturday and Sunday. Configurable via
`SimulatorConfig.settlement_delay_working_days`. Tier `synthesized_documented`
(the T+2 quote in §1); the specific cut-off clock is `synthesized_modelled`.

Refunds are **debit rows inside a batch**, not exclusions. This follows
Razorpay's published recon sample, in which `rfnd_DGRcGzZSLyEdg1` appears as a
row of `type: "refund"` with `debit: 242500` sharing a `settlement_id` with the
payment rows. Tier `synthesized_documented`.

The one exception is **full refund before the payment ever became eligible**. The
payment and its refund net to zero and neither is ever paid out. Both rows are
emitted with `settled: false`, `settlement_id: null`, `settled_at: null`. This is
the only sense in which "a refunded payment is not eligible" is true.

| case | payment | refund |
|---|---|---|
| full refund before `eligible_at` | never settles, `settled: false` | never settles, `settled: false` |
| partial refund before `eligible_at` | settles at **full** `amount − fee` | debit row, same or later batch |
| any refund after the payment settled | already settled | debit row in a **later** batch |

A refund's own `eligible_at` is its `created_at` — debits apply immediately.

---

## 4. Fee and tax — `credit = amount − fee`

Tier `captured_real`. Razorpay's payment-entity documentation defines
`fee` as **"Fee (including GST) charged by Razorpay"** and `tax` as "GST charged
for the payment". `tax` is a breakdown line *inside* `fee`, not an additional
charge.

**Verified on the captured account with zero residual:**

```
Σ(amount − fee) over captured+refunded  = 2,784,690
Σ(refund amount)                        =   450,000
expected balance                        = 2,334,690
GET /v1/balance                         = 2,334,690     delta = 0
```

Under the rejected identity `credit = amount − fee − tax` the expected balance is
off by exactly 10,270 — the sum of the `tax` column.

### 4.1 The exact fee formula, reverse-engineered

All 14 fee-bearing captured rows are reproduced **exactly, to the paise** by:

```
fee_excl_tax = ceil(amount * rate)
tax          = ceil(fee_excl_tax * 0.18)    # 18% GST, SAC 997158
fee          = fee_excl_tax + tax
credit       = amount - fee
```

14/14 exact, no residual. The ceiling on `tax` is what produces the observed
18.00%–18.06% effective band — e.g. `amount 76400 → fee_excl 1528 →
1528 × 0.18 = 275.04 → ceil 276`, matching the captured `tax: 276, fee: 1804`.

**The rounding algebra above is `captured_real`. The `rate` is not, except for
the two methods actually observed.**

### 4.2 What 14 rows license, and what they do not

The capture is **one account, one pricing plan, two methods** (netbanking ×9,
wallet ×3, plus 2 refunds and 1 failed payment), amounts ₹764–₹5,000.
**Zero card payments and zero UPI payments were observed** — card is WAF-blocked
on the ajax seeding path, UPI is disabled account-side. So:

| rate | value | tier | basis |
|---|---|---|---|
| netbanking, wallet | 2% | `captured_real` | 2.000000% on all 14 captured fee rows |
| Visa / Mastercard / RuPay **credit** | 2% | `synthesized_modelled` | Razorpay published pricing |
| **Amex, Diners** | **3%** | `synthesized_modelled` | Razorpay published pricing — these are *not* 2% |
| **UPI** | **2%** | `synthesized_modelled` | Razorpay published pricing |
| **RuPay debit** | **0%** | `synthesized_modelled` | Sec 269SU IT Act / Sec 10A PSS Act |

Nothing here transfers to a negotiated plan. Production pricing is a
per-merchant matrix; this is a flat card at one tier.

#### UPI is billed, and saying otherwise would be a false claim about a vendor

Zero-MDR for domestic UPI P2M (Sec 269SU IT Act, Sec 10A PSS Act, CBDT Circular
32/2019) binds **banks and system providers**. It does not stop a payment
aggregator charging a platform fee, and **Razorpay's published pricing bills UPI
at the same 2% platform fee as every other domestic instrument**, plus 18% GST.

An earlier draft of this spec priced UPI at zero and called it a degenerate
case. That was wrong, and it would have been a confident false statement about
Razorpay's own commercials. UPI is billed here like everything else.

RuPay **debit** is modelled at zero on the statutory reading rather than
Razorpay's table, which does not itemise it. That is `synthesized_modelled` and
it is the weaker of the two claims on this page; it is flagged as such rather
than smoothed over.

### 4.3 The degenerate case is `tax == 0`, not `fee == 0`

The two candidate identities differ by exactly `tax`. So a row is
**indistinguishable** between them whenever `tax == 0`, whatever its fee:

```
amount - fee        == amount - fee - 0
```

Razorpay's own published recon sample is degenerate on its payment row
(`amount 100000, fee 2900, tax 0`), which is exactly why the wrong identity is
easy to adopt from the documentation. The dataset therefore plants both shapes:

- `fee > 0, tax = 0` — the published sample's shape;
- `fee = 0, tax = 0` — RuPay debit at zero MDR.

An analyzer testing both hypotheses must report **INDECISIVE** on these rows
rather than counting them as confirmation.

Failed payments carry **`fee: null, tax: null`** — not `0`. This is
`captured_real` (`pay_TSi7iYzv9ycljW`, verbatim in
`spike/captured_dataset.json`), and any statement that they carry zero is
wrong. They never appear in a batch.

### 4.4 No floats, ever

Every monetary quantity is an `int` in paise, in the data and in the simulator.
Rupee figures appear only in `bank_statement.csv` and the ERP/GST companions,
formatted from integer paise by `divmod(paise, 100)` — never by float division.

---

## 5. Recon row schema and its verified quirks

The emitted row shape is Razorpay's `GET /v1/settlements/recon/combined` item,
field order preserved from the published sample. Every quirk below is reproduced
deliberately and is asserted by `tests/test_generator_schema.py`.

| quirk | rule | tier |
|---|---|---|
| id field split | `entity_id` holds the row's own id; `payment_id` is **null on `payment` rows** and populated only on rows *pointing at* a payment. Resolution rule: `entity_id if type == 'payment' else payment_id` | `captured_real` / doc sample |
| `credit_type` absence | the key is **omitted entirely** on `adjustment` rows — not null | doc sample |
| `settlement_utr` on adjustments | **null** even when the row carries a real `settlement_id`. UTR is therefore **not** a batch-level key: join on `settlement_id`, treat UTR as a hint | doc sample |
| `notes` polymorphism | `{}` when populated, `[]` when empty — **never null** in captured data (14 objects, 1 empty array across 15 payments). A parser typed `notes: dict` crashes on the empty case | `captured_real` |
| adjustment rows are unjoinable | no `payment_id`, no `order_id`, no `method`. They **cannot** be matched by the normal join path and must route to the exception queue by construction | doc sample |
| failed payments | `fee: null, tax: null`, `captured: false`, never in any batch | `captured_real` |
| paise integers | all amounts in currency subunits | `captured_real` |

Razorpay's published sample additionally shows `notes` as a bare **string** and
as **null**. The generator restricts itself to the empirically observed `{}` /
`[]` forms so that `tests/test_generator_schema.py` can assert a tight invariant;
consumers of the real API must still treat `notes` as fully polymorphic
(`object | array | string | null`).

Transfer rows (`type: "transfer"`) exist in the published sample but are **out of
scope** for this dataset — Razorpay Route was never exercised on the captured
account and no class in the test plan depends on them.

---

## 6. Disputes

`POST /v1/disputes` returns HTTP 404 `{"message":"no Route matched with those
values"}` — a routing-layer 404. The endpoint does not exist in test or live
mode. Disputes are raised by the issuing bank; there is no simulator. Dispute
behaviour here is therefore modelled, tier `synthesized_documented` for the
recon-row consequences and `synthesized_modelled` for reason codes and timing.

| dispute state | recon consequence |
|---|---|
| open / under_review | `dispute_id` populated, `on_hold: true`, `settled: false`, credit excluded from live balance, **dropped from its batch** |
| won | hold clears, payment settles in a **much later** batch — `created_at` and `settled_at` diverge widely |
| lost | `amount_deducted` becomes non-zero and surfaces as a separate `type: "adjustment"` **debit** row with no `payment_id`, `order_id` or `method` |

### 6.1 Dispute timing must make the modelled state reachable

A hold can only drop a payment from its batch if the dispute opens **before**
`eligible_at`. A true chargeback does not: it arrives weeks after the payment
has already been paid out, and the money is recovered by a debit adjustment
rather than withheld. Modelling both with the same timing produces an
incoherent ledger — a payment that "settled later because of a hold" whose hold
began after it had already settled.

The generator therefore splits disputes by phase:

| phase | opens | mechanism |
|---|---|---|
| `retrieval`, `fraud` | within the T+2 window, before `eligible_at` | withholds — `on_hold: true`, dropped from the batch |
| `chargeback` | 20–45 days after capture, after the payment settled | claws back — `type: "adjustment"` debit row |

Tier `synthesized_modelled`. Razorpay documents no dispute timing distribution;
this is card-network practice. `tests/test_state_transitions.py` asserts the
resulting states are reachable — a held payment is never already settled, and a
lost-dispute adjustment never predates its dispute.

A held payment and a subset-sum-excluded payment both fail to appear in their
expected batch for **different reasons**, and the reconciliation engine must
distinguish them. That is the point of planting both.

---

## 7. Determinism

Single `random.Random(seed)`; no reliance on set or dict iteration order
anywhere; all collections sorted by explicit key before iteration; JSON written
with a fixed field order and `ensure_ascii=False`, CSV with `\n` line endings and
a fixed column order. Same seed ⇒ byte-identical output, asserted three
consecutive runs in `tests/test_determinism.py`.

---

## 8. Ground truth isolation

`ground_truth/ground_truth.json` holds the `payment_id → settlement_id` mapping,
the true decomposition of every batch, the ambiguity register, and the class
label of every planted row. **No solver module may read this path.**
`tests/test_no_leakage.py` asserts that no scenario label, class name or
ground-truth token appears anywhere in the solver-visible data files, that entity
ids encode nothing, that hard rows are not clustered in file order, and that
`notes` **keys and values** carry no class information.
`tests/test_classes.py::test_source_tier_is_not_a_shortcut_to_hard_cases`
asserts the provenance tier is not usable as a shortcut.

### 8.1 Two leaks that independent audit found here

Both were real, both shipped in an earlier draft, and both are recorded because
the way they were found is the point.

1. **`source_ref` named the mechanism.** Calibration debits carried
   `"ambiguity-calibration debit"` and `"balance-pressure debit"`. A two-token
   `grep` over `recon_combined.json` identified **both** provably-unresolvable
   batches. `source_ref` now describes a row's *provenance* and never the
   generator's *purpose*.
2. **A `notes` value was a 100%-precision marker.** Calibration refunds used
   `{"reason": "partial_cancellation"}` while organic refunds drew from a
   disjoint list, so `grep partial_cancellation` found every calibrated batch.
   Both now draw from the same pool, and the leakage test compares
   `(key, value)` pairs rather than keys alone.

The lesson generalises: a provenance field that explains *why the generator
made a row* is a stage direction, and stage directions leak.

---

## 9. The companion files — bank, ERP and GST

Three files sit alongside the recon rows. Each exists to break a different
join.

### 9.1 `bank_statement.csv` — the only source of truth for money received

One line per batch: `utr, date, narration, amount`. Amounts are rupee strings
formatted from integer paise by `divmod`, never by float division — a bank
statement is where a reconciliation engine actually meets decimal input.

Three narrations are deliberately lossy (truncated mid-string, UTR masked, or
replaced with a generic fragment). On **one** of those the `utr` column itself
is blank, so the join key is gone entirely and a matcher must fall back to
`(amount, date)`. That fallback is asserted to be unambiguous across the file,
so the row is recoverable — but only by a matcher that has the fallback.

### 9.2 `erp_orders.csv` — the merchant's sales ledger

`order_id, invoice_no, gstin, amount, invoice_date`. Joins to payment rows on
`order_id`, and breaks in both directions by design: some settled payments have
**no ERP order at all**, and some ERP invoices have **no payment**. The
missing-in-ERP sample is drawn from *settled* payments specifically — an
unsettled payment reasonably has no invoice yet, so sampling those would not
test the invariant that matters (money received, nothing in the books).

Most orders carry **no `gstin`**: they are B2C retail, where the customer has no
registration and the document is a bill of supply rather than a B2B tax invoice.
An all-B2B retail book would be unrealistic at these ticket sizes.

### 9.3 `gstr2b.csv` — the merchant's inward-supply ITC statement

This is the **purchase** side, not the sales side. The merchant's input tax
credit on Razorpay's MDR rides on **Razorpay's tax invoice for its fee**, and
that invoice is what must appear in GSTR-2B.

**Razorpay invoices monthly, not per settlement.** Fees are deducted per
settlement but consolidated into one tax invoice generated at the start of the
following month. So **one 2B line must tie back to N settlements' fee columns** —
which is both the real shape and a harder reconciliation than one line per batch.

Columns beyond the statutory minimum are present because the ITC decision
depends on them: `gstr1_filing_period`, `supplier_gstr3b_filed`, and
`itc_availability`.

#### The GST arithmetic does not tie to the paise, and that is correct

A real consolidated invoice computes GST **once on the aggregate taxable value**
(`CGST = ceil(taxable × 9%)`, `SGST` identically, so the halves are equal and
the total ties to the rate). The ledger accrues **ceiling-rounded tax per
transaction**. These two numbers differ by a few paise per month. That gap is a
genuine reconciliation residual, and it is recorded in the ground-truth key as
`gst_rounding_residuals` rather than papered over by forcing one side to match.

A fee charged with **no GST component** (the `tax: 0` rows of §4.3) carries no
ITC, so it is excluded from the invoice's taxable value and tracked separately
as `fee_charged_without_gst_paise`.

#### Three distinct statutory grounds for ITC at risk

| ground | provision | how it presents |
|---|---|---|
| invoice never reached 2B | **Sec 16(2)(aa) CGST** | the line is simply absent — the supplier never furnished it in GSTR-1, so there is nothing for the recipient to accept under the IMS regime and nothing populates 2B |
| supplier's invoice carries no valid IRN | **Rule 48(5) CGST** | `irn` blank, `itc_availability: No`. A notified supplier's invoice issued otherwise than under Rule 48(4) is **not a tax invoice**, so ITC fails for want of a valid document |
| supplier has not filed GSTR-3B | **Rule 37A CGST** | `supplier_gstr3b_filed: N` while `itc_availability` still reads **Yes**. 2B does *not* flag this — it is a condition the recon engine has to compute, which is why it is the interesting exposure. ITC validly taken must be reversed, with interest |

**The "IRN generated more than 30 days late" scenario is deliberately NOT
modelled, because it is mechanically impossible.** The 30-day reporting window
(AATO ≥ ₹10 crore, effective 1 April 2025) is enforced by the IRP *refusing to
register the document*. There is no late IRN — there is no IRN at all, the
invoice never auto-populates into GSTR-1 or GSTR-2B, and a row that is
simultaneously present in 2B and late-IRN cannot exist. An earlier draft planted
exactly that row and asserted it in a test. Rule 48(5) replaces it.

Tier: the GST layer is `synthesized_modelled` throughout. Razorpay's fee invoice
was never captured — test mode produced no settlement and therefore no fee
invoice.

#### The GSTINs are unissuable by construction

Every generated GSTIN is checksum-valid but carries `X` as the PAN
entity-type character, which is **not in the issued set** `ABCFGHLJPTKE`. No such
PAN can exist, so no generated GSTIN can collide with a real registration. This
is a construction guarantee, not luck.

The Razorpay GSTIN in this dataset is synthetic and is **deliberately not**
Razorpay's real registration `29AAGCR4375J1ZU`.

Merchant and supplier are both modelled in Karnataka (state code 29), so the fee
invoice is intra-state CGST + SGST under Sec 12(2)(a) IGST Act. **That is a
property of the merchant chosen, not a rule** — most Razorpay merchants sit
outside Karnataka and receive IGST. Third-party vendor lines in the same file
exercise the IGST path.

---

## 10. Scope — what is in, what is out, and why

Silence reads as ignorance. Everything below was considered and decided.

### In scope

Payments, refunds, adjustments; T+2 batching under the documented rule; dispute
holds and chargeback clawbacks; roll-forward; netting; ambiguity; cross-month
timing; the schema quirk list; bank / ERP / GSTR-2B reconciliation.

### Out of scope, with the reason

| omitted | why |
|---|---|
| **Instant settlements** | permanently unavailable in test mode — `reason: "instant_settlements_test_mode_blocked"`, reproduced through REST, MCP and CLI. They also carry a *different* fee model (a percentage of the settled amount, as its own row) and bypass the batching rule entirely, so modelling them would mean inventing a second unobserved mechanism |
| **Route transfers** (`type: "transfer"`) | present in Razorpay's published sample but never exercised on the captured account, and no class in the test plan depends on them |
| **Settlement reversals / failed payouts** | the most common real recon exception at any aggregator, and **genuinely absent here**. Modelling one requires a bank-side debit reversing a prior credit and a re-settlement under a new UTR — a second bank-statement shape this dataset does not have. Named as a gap rather than quietly omitted |
| **International / multi-currency** | different settlement cycle, different rate card, FX. Single-currency INR only |
| **TDS u/s 194-O** | applicability to a *payment aggregator* is contested — CBDT has issued PG/PA carve-outs — so its absence is arguably correct rather than an oversight. Not claimed either way |
| **TCS u/s 52 CGST** | an e-commerce operator obligation, not an aggregator's, on this fact pattern |
| **Negotiated pricing tiers, TDR slabs, debit-card caps** | one flat rate card; see §4.2 |

### Exercised but bounded

| mechanism | bound |
|---|---|
| exact subset-sum | degrades to FIFO above `max_pool`; see §1.5 |
| ambiguity enumeration | truncates above 64 tying subsets, recorded on the batch |
| negative live balance | debits defer largest-first (§1.4). The dataset contains a batch where this **actually fires** — a rule that never executes is a rule that was never tested |

---

## 11. Robustness — the answer to "you tuned it until it worked"

The dataset is a pure function of one integer. A commit timestamp proves the
bytes existed at a time; it cannot prove nobody tried seeds until the numbers
looked good.

`engine/robustness.py` runs the generator across seeds `0..19` and writes
`ROBUSTNESS.md`: min / median / max for every planted class, and the count of
seeds where each class came out empty. `tests/test_robustness.py` asserts the
core classes survive five seeds chosen as "the first five integers."

The shipped dataset uses seed `20260822`. It was selected **only** to land on
exactly 240 rows. No other property was selected for, and the robustness table
is what demonstrates that.
