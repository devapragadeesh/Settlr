# Track 01: Agentic Commerce

## NPCI Unified Agent Protocol status
UAP is under development at NPCI in industry consultation, NOT published. No circular, no spec PDF, no sandbox. Requires RBI approval before rollout, not granted as of August 2026. Design intent is a trusted registry and verification layer for AI agents, with per-agent spend limits, merchant scoping, user consent, audit trails. Builds on UPI Circle delegated payments.

What is actually live is UPI Reserve Pay: a user authorises a single per-merchant spending limit, after which multiple debits happen without repeated PIN.

## Protocol race
Agentic Commerce Protocol (ACP) from OpenAI and Stripe, Apache-2.0, covers Checkout, Delegate Payment, Feed, Cart, Orders, Auth, MCP binding.
Universal Commerce Protocol (UCP) from Google, Shopify and retailers. Capability manifest at /.well-known/ucp, REST plus A2A and MCP bindings, signed requests, idempotency keys.
AP2 from Google, donated to FIDO Alliance. Mandates are cryptographically signed intent and cart artifacts.
x402 from Coinbase, now under Linux Foundation. HTTP 402 plus USDC settlement for machine-to-machine. Wrong rail for an India UPI audience.
Visa Trusted Agent Protocol and Mastercard Agent Pay are partner-gated.

The payment layer is consolidating. The contested layer is merchant-side commerce semantics: ACP Feed versus UCP capability manifest. Neither has an India-native answer and neither speaks UPI.

## Agent-readable catalog convention
Three layers: static discovery via agents.md, capability manifest at /.well-known/ucp or ACP Feed, live interactive via MCP. Convention is agents.md then well-known manifest then MCP tools then ACP/UCP checkout session then AP2-style signed mandate.

## Saturation
Saturated and derivative: chat checkout widget, MCP wrapper over Razorpay API, upsell recommender, abandoned cart WhatsApp bot, llms.txt generator.
Genuinely open: the safety, consent and dispute layer for India-specific rails; agent identity and reputation for merchants; reconciliation of agent-initiated payments; bridging UPI Reserve Pay mandate semantics with ACP/UCP session semantics.

## Best build: Mandate Broker
A merchant-side service exposing /.well-known/ucp plus ACP-compatible checkout endpoints. Before any debit the broker mints an AP2-style signed mandate with agent identity, merchant scope, per-transaction and cumulative caps, category allowlist, TTL, revocation URL, persisted to a hash-chained append-only ledger. Every Razorpay test-mode call is gated by a policy engine emitting a human-readable explanation. Failure demo: agent exceeds cap, gets a signed denial receipt, then step-up human approval, then live revoke kills a recurring debit.
