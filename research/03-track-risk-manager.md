# Track 02: AI Risk Manager

## The Indian loss landscape
RTO (return to origin) is the biggest India-specific loss class. Industry-reported 20-25% overall RTO, up to 40% in COD-heavy fashion. Prepaid RTO under 2% versus 28-35% for COD. These are vendor-blog numbers, not audited.

UPI fraud is high volume but small per transaction. UPI is push-payment and has no merchant-side chargeback in the card sense, so a UPI chargeback responder is a bank-side product, not a merchant one. Card chargebacks and RTO are where merchant money actually leaks.

RBI Master Direction on Payment Aggregators (September 2025) mandates a board-approved dispute resolution policy with defined refund timelines plus fraud detection systems.

## Razorpay's existing stack
Thirdwatch merged into Magic Checkout. Does pre-order COD and RTO risk with device and behavioural signals, device-cluster linking, address-gibberish detection. Merchant surface is an RTO Analytics Dashboard.

The gap: Razorpay publishes no precision, no recall, no false-positive cost, no calibration. Only business outcomes (40% more conversions, 30% lesser RTOs). The dashboard is descriptive analytics with no threshold tuning and no cost curve. Thirdwatch is pre-confirmation only, so there is no post-order risk layer.

## The data problem
There is no public Indian RTO dataset. Available options are IEEE-CIS Fraud Detection (real card-not-present fraud, US, rich raw features, entity IDs), ULB credit card (PCA features make feature engineering impossible), PaySim (synthetic mobile money, closest structural analogue to UPI), Sparkov (synthetic US cards).

Critical asymmetry: in fraud detection, ground truth is your own generative choice. You plant the fraud then detect it, which is circular. Synthetic tabular generators fail to preserve temporal, velocity and multi-account fraud signals, which are exactly the signals a model would claim to learn.

## Techniques
Tractable: cost-sensitive learning with false-positive cost curves, conformal prediction for calibrated abstention, gradient boosting as the workhorse, simple graph features via connected components over shared device/IP/address/phone, LLM as evidence assembler, drift detection.
Traps: training a graph neural net end to end, embedding-based entity resolution from scratch, any LLM in the scoring loop.

## Best build: RTO Guard
Cost-calibrated COD decision engine. LightGBM plus connected-component graph features, split-conformal for a review band, threshold chosen by expected-rupee optimisation. Live false-positive cost slider so judges drag the cost of a lost good order and watch optimal threshold and net rupees move.
