# Track 04: AI Finance Controller — the chosen track

## What must be matched
The loop is four-way, not two-way: order and ERP gross, PG payment captured, PG settlement batch net, bank credit with UTR, and GST tax lines.

## Verified recon API schema
GET /v1/settlements/recon/combined?year=yyyy&month=mm returns entity_id, type, debit, credit, amount, currency, fee, tax, on_hold, settled, created_at, settled_at, settlement_id, description, notes, payment_id, settlement_utr, order_id, order_receipt, method, card_network, card_issuer, card_type, dispute_id. Amounts are in paise.

Arithmetic identity: for payments credit equals amount minus fee minus tax. Across a settlement batch, the sum of credits minus the sum of debits equals the bank credit for that UTR.

## Verified subset-sum behaviour
Razorpay states verbatim that when settling transactions they will only choose the ones that add up to your current live balance. A settlement batch is therefore a subset-sum of eligible payments, not all of T-2's payments. This is the justification for the constraint solver and the reason naive one-to-one matching caps out.

## Breakage causes ranked
Netting and aggregation, where one bank credit equals many payments minus refunds minus adjustments. Partial settlements. T+2 timing versus instant settlements with separate fees and UTRs. Fee and TDR variance where actual fee differs from contracted MDR per instrument. Refunds netted off in a different month from the sale. Chargebacks returning weeks later as unlabelled adjustment rows. Route split settlements with transfer rows and on_hold flags. Bank narration truncation killing the UTR. Paise-level rounding.

## Verified white space
Optimizer Single View Reconciliation consolidates payments and settlements across gateways into one dashboard, showing status, UTR, settlement IDs, gateway fees and settlement-to-payment mapping. It does NOT cover GST or tax lines, ERP matching, accounting software connectivity, or automated bank statement matching. Its only stated limitation is late authorizations.

Agent Studio's Settlement Insights is only a daily WhatsApp summary. Cashflow Forecaster only predicts three to seven days ahead and is a notifier, not an actuator. Neither reconciles anything.

## India compliance layer
GSTR-2B is the legal gate for input tax credit under section 16(2)(aa) CGST. You can only claim what your supplier filed. Invoice Management System becomes mandatory from 1 April 2026. Rule 37A requires reversing ITC if the supplier did not file GSTR-3B by 30 September following the financial year.

TCS under GST section 52 is 1% of net taxable supplies by ecommerce operators, filed monthly in GSTR-8. TDS section 194-O is 0.1% on gross with a 5 lakh threshold for individuals and nil threshold for companies.

E-invoicing is mandatory at annual turnover of 5 crore, with a 30-day IRN reporting window above 10 crore. A check for settled payments with no valid IRN is a strong demo line.

India is harder than the US because US reconciliation is payout to bank to general ledger under one tax regime with no ITC gate. India adds a legally binding third-party statement you do not control, two parallel withholding regimes deducted by the same operator, an invoice registration clock, and paise-level netting across mixed settlement cycles.

## Architecture: the four-stage cascade
Stage 1 exact-key join on payment_id, order_id, settlement_id and UTR, clearing 70-85%.
Stage 2 blocking and fuzzy candidate generation with a plus or minus three day window, amount tolerance, and narration token overlap via rapidfuzz. Embeddings only for free-text narration; for structured IDs string distance is strictly better.
Stage 3 constrained optimization. Hungarian algorithm via scipy linear_sum_assignment for one-to-one residuals. Subset-sum, min-cost flow or integer linear programming via PuLP or OR-Tools for the netting case. This is the technical differentiator.
Stage 4 LLM only at the exception boundary, classifying why a residual is unmatched, drafting the narrative, proposing the journal entry.

Governing rule: LLM as explainer and LLM as router, never LLM as matcher. Matching is arithmetic. An LLM asked to match rows will hallucinate, be non-deterministic across runs, and cannot show a proof.

Realistic targets: stage 1 around 75%, plus stage 2 around 88%, plus stage 3 around 94-97%, with 3-6% genuinely unresolvable.

## Saturation
Will look derivative: AI bookkeeper, generic bank statement categorizer, LLM-wrapper close checklist, Stripe-style payout matcher, GSTR-2B recon that is just a chat box. Competitors include Basis, Numeric, Ramp, Truewind, Klarity, HighRadius, ZenStatement, ClearTax.
Will look novel: constraint-solver netting on the real Razorpay schema plus the tax leg plus an exception ledger with evidence.
