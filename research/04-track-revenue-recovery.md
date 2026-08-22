# Track 03: AI Revenue Recovery

## Razorpay already ships this
Agent Studio ships Subscription Recovery and Abandoned Cart Conversion. Razorpay also announced an Intelligent Retry Engine in beta under Intelligent Revenue-Protect: configurable retry cadence and templates, smart retries timed on user context and bank availability, WhatsApp recovery links for registration drop-offs and failed debits, smart routing on latency or downtime. VERIFIED.

## Payment failure reality
Merchant-side blended UPI success is 92-96%. NPCI circular OC-149 sets a technical decline target under 1% and business decline target under 5%. NPCI publishes per-bank monthly technical decline, business decline and uptime data, a real citable public dataset.

Named Razorpay error reasons drive intervention routing:
bank_technical_error and gateway_technical_error mean issuer or PSP downtime, so retry after downtime clears.
insufficient_funds means delay to payday or salary cycle.
payment_collect_request_expired and payment_timed_out are UX issues, so re-prompt immediately.
invalid_vpa and vpa_resolution_failed mean the instrument is wrong, so retry is guaranteed to fail and you must collect a new VPA.
card_expired, card_not_enrolled, card_disabled_for_online_payments, debit_instrument_blocked mean the instrument is dead, so never retry.
transaction_limit_exceeded means split or use an alternative method.

The Downtime API gives live outage state for cards, netbanking and UPI. This is the key input for not retrying into a dead bank.

Razorpay default subscription retry is T+1, T+2, T+3, once per day, three attempts, then pending then halted.

## Mandate compliance
RBI e-mandate requires pre-debit notification at least 24 hours before debit, stating amount, date and merchant name. Additional factor authentication threshold is 15,000 rupees generally, 1 lakh for mutual funds, insurance and credit card bills.

NPCI August 2025 Autopay circular allows one original execution plus a maximum of three retries per mandate sequence number. Executions must be scheduled in non-peak hours only, where peak is 10:00 to 13:00 and 17:00 to 21:30 IST.

UPI Autopay failure rate is 8-15% versus 2-3% for card mandates, with around 20 million autopay revocations per month driven by low balances.

A legal retry sequencer is therefore a constrained optimizer, not an ML free-for-all.

## B2B receivables
MSMED Act section 15 requires payment to micro and small suppliers in 15 days, maximum 45 days with written agreement. Section 43B(h) of the Income Tax Act means overdue MSME payables are disallowed as a deduction until actually paid, converting late payment into a tax hit. Interest penalty is three times the RBI bank rate, compounded monthly.

This is the strongest hook in the track: an AI chaser can quantify the buyer's tax disallowance exposure per open invoice and use it as the escalation argument.

RBI Fair Practices Code limits collections contact to 08:00 to 19:00, prohibits abusive language and prohibits contacting family, employer or neighbours.

## Hinglish voice
Sarvam AI Bulbul TTS generates Hinglish in a single pass with no language-boundary pause. Saaras ASR beats Whisper on code-switching. Cartesia, ElevenLabs and Deepgram have lower latency but none match Sarvam on native Hinglish code-mixing.

TRAI compliance is the trap question. DLT registration is mandatory for every principal entity, and TRAI makes no distinction between an AI bot and a human for commercial calls. 140-series is promotional, 1600-series is transactional. DND scrubbing is required before every campaign.

## Saturation
Checkout drop-off recovery is the most saturated direction in the entire event. Failed-subscription recovery is already Agent Studio product. B2B receivables and promise-to-pay tracking are the least crowded.
