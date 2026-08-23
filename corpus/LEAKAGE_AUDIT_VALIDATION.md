# LEAKAGE AUDIT VALIDATION -- against the FROZEN primary dataset

The audit is run against the dataset whose four data defects are
already known. It must rediscover them WITHOUT being told what to
look for. An audit that cannot find a known leak is not evidence
about the leaks nobody has found yet.

## D4 -- REDISCOVERED
required: the bank file must be reported NOT INDEPENDENT
found:    posting lag (days) distribution: {0: 12}   <-- CONSTANT: the bank has no clock of its own; narrations embedding their own reference verbatim: 9/12; LEDGER FIELDS RECOVERABLE FROM THE BANK FILE: settled_at, settlement_utr

## D5 -- REDISCOVERED
required: the MINTED rows must be separable from organic ones -- the amount column alone should do it, before any description string is read
found:    single_column  recon   prec=1.000 rec=0.500 lift= 40.0x p=8.79e-06 LEAK [uncertified]  description == 'Settlement processing fee'

## D6 -- REDISCOVERED
required: the orphan invoices must be found by invoice-number RANK; a file-position check passes this dataset, because they are interleaved by position
found:    ordering       erp     prec=1.000 rec=1.000 lift= 30.7x p=2.01e-11 LEAK [certified]  the 6 highest values of invoice_no

## D7 -- REDISCOVERED
required: the decoy class must be reported INEFFECTIVE: it equalises `amount`, but the arithmetic runs on `credit`, and the tiers differ
found:    INEFFECTIVE D7_decoy_payments                  1/4  pairs collide on `credit` (delta 0)  -- observed credit deltas [-8711, -3670, 0, 11732]

## VALIDATION: PASS

# LEAKAGE AUDIT -- /Users/deva/razorpay/engine/data

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 12
    posting lag (days) distribution: {0: 12}   <-- CONSTANT: the bank has no clock of its own
    narrations embedding their own reference verbatim: 9/12
    LEDGER FIELDS RECOVERABLE FROM THE BANK FILE: settled_at, settlement_utr
    BANK REFERENCE IS DERIVABLE: '1781695800KVmUoi' contains settlement_id[-6:] 'KVmUoi'; '1781695800KVmUoi' starts with settled_at 1781695800; '17823006005FpBtT' contains settlement_id[-6:] '5FpBtT'; '17823006005FpBtT' starts with settled_at 1782300600; '1782905400L2YMb0' contains settlement_id[-6:] 'L2YMb0'; '1782905400L2YMb0' starts with settled_at 1782905400
    VERDICT: bank is NOT INDEPENDENT

## Per-class strongest separator

  D5_minted_calibration_rows                   LEAK single_column  recon   prec=1.000 rec=0.500 lift= 40.0x p=8.79e-06 LEAK [uncertified]  description == 'Settlement processing fee'
                                                    (not statistically certified at this class size -- alpha needs p <= 3.3e-03; the effect size gates the build, see ALPHA)
  D5_rows_of_ambiguous_batches                 LEAK single_column  recon   prec=1.000 rec=0.526 lift=  6.3x p=4.59e-19 LEAK [certified]  settled_at == 1783510200
  D5_rows_of_calibrated_batches                ok   single_column  recon   prec=0.510 rec=1.000 lift=  1.2x p=1.42e-11      [certified]  settled_at >= 1.7823e+09
  D6_erp_orphan_invoices                       LEAK ordering       erp     prec=1.000 rec=1.000 lift= 30.7x p=2.01e-11 LEAK [certified]  the 6 highest values of invoice_no
  D7_decoy_payments                            ok   column_pair    recon   prec=1.000 rec=0.250 lift= 30.0x p=9.76e-04      [uncertified]  (card_issuer == 'SBIN') AND (card_type == 'debit')
  itc_at_risk                                  UNTESTABLE  (class size 2 < 3) 
  payments_missing_from_erp                    ok   column_pair    recon   prec=0.286 rec=0.429 lift=  4.9x p=4.14e-04      [uncertified]  (debit == 0) AND (settlement_utr == '1786534200yuev1Q')

## Class efficacy -- did the class do what it claims?

    INEFFECTIVE D7_decoy_payments                  1/4  pairs collide on `credit` (delta 0)  -- observed credit deltas [-8711, -3670, 0, 11732]
    ok   incidental_credit_collisions       4/4  baseline, for comparison  -- 4 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 1200573 inside 1200573
    derivability   settlement_utr = contains settled_at verbatim [100.0% of rows]  e.g. 1781695800 inside 1781695800KVmUoi
    derivability   settlement_utr = settled_at concatenated with a slice of settlement_id [100.0% of rows]  e.g. 1781695800KVmUoi = settled_at(1781695800) + settlement_id[..KVmUoi]

## VERDICT: FAIL

classes with a significant separator: D5_minted_calibration_rows, D5_rows_of_ambiguous_batches, D6_erp_orphan_invoices
bank statement is not an independent source
classes that do not achieve what they claim: D7_decoy_payments
