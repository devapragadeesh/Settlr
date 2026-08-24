# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A10_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 5, 1: 6, 2: 4, 5: 5}
    narrations embedding their own reference verbatim: 12/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 27059.3
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.250 lift= 35.2x p=2.84e-02      [uncertified]  order_id CONTAINS 'mijictgf8velrk'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.308 rec=0.444 lift=  5.9x p=2.01e-03      [uncertified]  (created_at <= 1.80125e+09) AND (credit >= 839606)
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.2x p=2.07e-05      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.667 rec=0.333 lift= 19.2x p=2.98e-03      [uncertified]  (created_at >= 1.80389e+09) AND (settled_at == 1804073400)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.600 rec=0.600 lift=  5.2x p=1.07e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2, 2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       19/19  baseline, for comparison  -- 19 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 404700 inside 404700

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A20_B0_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 7, 1: 4, 2: 3, 5: 4, 6: 2}
    narrations embedding their own reference verbatim: 17/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 38141.3
  d04_unattested_settlements                   UNTESTABLE  (class size 12 < 3) DEGENERATE: the class is 12/12 of the table, so it cannot be separated FROM it -- it IS it
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 31.9x p=3.14e-02      [uncertified]  order_id CONTAINS 'qmvi1pqperoxhn'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=1.000 rec=0.118 lift= 18.5x p=2.77e-03      [uncertified]  (amount >= 7.6e+06) AND (method == 'netbanking')
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=1.000 rec=0.167 lift= 26.2x p=1.34e-03      [uncertified]  (amount >= 5.2099e+06) AND (created_at >= 1.80626e+09)
  d07_decoy_credit_near_collision              ok   single_column  recon   prec=1.000 rec=0.167 lift= 52.3x p=1.91e-02      [uncertified]  notes['cart_id'] == 'crt_040016'
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.8x p=1.13e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 3/3  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1, 1, 1]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       34/34  baseline, for comparison  -- 34 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 173700 inside 173700

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A20_B100_Cfifo

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 5, 1: 6, 2: 3, 5: 5, 6: 1}
    narrations embedding their own reference verbatim: 13/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 26196.3
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 32.0x p=3.12e-02      [uncertified]  order_id CONTAINS 'nugkp0sr6wt7x8'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=1.000 rec=0.125 lift= 19.6x p=2.44e-03      [uncertified]  (card_issuer == 'AXIS') AND (card_network == 'MasterCard')
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.417 rec=0.417 lift= 10.9x p=2.23e-05      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=1.000 rec=0.333 lift= 52.3x p=3.05e-04      [uncertified]  (amount >= 3.0149e+06) AND (created_at <= 1.79965e+09)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.8x p=1.13e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2, -2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       35/35  baseline, for comparison  -- 35 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 660000 inside 660000

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A20_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 10, 1: 3, 2: 2, 5: 3, 6: 2}
    narrations embedding their own reference verbatim: 17/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 33925.4
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 31.9x p=3.14e-02      [uncertified]  order_id CONTAINS 'xt4ahyly9tncbl'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=1.000 rec=0.176 lift= 18.5x p=1.33e-04      [uncertified]  (amount >= 7.6149e+06) AND (created_at >= 1.80421e+09)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=0.333 rec=0.333 lift=  8.7x p=5.21e-04      [uncertified]  (amount >= 5.4049e+06) AND (settled_at >= 1.80407e+09)
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=1.000 rec=0.333 lift= 52.3x p=3.05e-04      [uncertified]  (created_at <= 1.79973e+09) AND (settled_at == 1800444600)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.8x p=1.13e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, 1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       35/35  baseline, for comparison  -- 35 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 105000 inside 105000

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A20_B100_Crandom

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 6, 1: 5, 2: 5, 5: 3, 6: 1}
    narrations embedding their own reference verbatim: 15/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 32030.7
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   column_pair    erp     prec=1.000 rec=0.125 lift= 31.9x p=3.14e-02      [uncertified]  (amount CONTAINS '3897.00') AND (gstin IS NULL/blank)
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.667 rec=0.118 lift= 12.3x p=8.04e-03      [uncertified]  (notes['warehouse'] == 'MAA-1') AND (settled_at <= 1.80044e+09)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=0.500 rec=0.167 lift= 13.1x p=7.72e-03      [uncertified]  (fee >= 35046) AND (settled_at == 1804073400)
  d07_decoy_credit_near_collision              ok   single_column  recon   prec=1.000 rec=0.167 lift= 52.3x p=1.91e-02      [uncertified]  notes['cart_id'] == 'crt_046086'
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.8x p=1.13e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1, 1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       28/28  baseline, for comparison  -- 28 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 3079900 inside 3079900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A20_B100_Crandom0

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 4, 1: 5, 2: 5, 5: 6}
    narrations embedding their own reference verbatim: 15/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 32102.1
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 31.9x p=3.14e-02      [uncertified]  order_id CONTAINS 'sqrdsaqmmhfwrg'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.800 rec=0.235 lift= 14.8x p=2.89e-05      [uncertified]  (card_issuer == 'SBIN') AND (settled_at <= 1.80165e+09)
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.417 rec=0.417 lift= 10.9x p=2.23e-05      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.500 rec=0.600 lift= 31.4x p=3.86e-05      [uncertified]  (amount <= 169902) AND (settlement_utr == 'RATN27036736005')
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.600 rec=0.600 lift=  9.4x p=8.38e-12      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 3/3  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1, 1, 1]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       34/34  baseline, for comparison  -- 34 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 96600 inside 96600

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A20_B50_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 7, 1: 3, 2: 5, 5: 3, 6: 2}
    narrations embedding their own reference verbatim: 13/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 27115
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d04_unattested_settlements                   UNDERPOWERED  single_column  settlement_report prec=0.545 rec=1.000 lift=  1.1x p=5.00e-01      [uncertified]  reported_reference IS NOT NULL/blank
                                                    (class size 6 of 12: even a PERFECT separator could only reach p=1.1e-03, above alpha=9.3e-05. Not certifiable clean OR leaking -- reported, not gated)
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 32.0x p=3.12e-02      [uncertified]  order_id CONTAINS '0x9wnlgrbzgwlt'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=1.000 rec=0.125 lift= 19.6x p=2.44e-03      [uncertified]  (amount >= 7.8049e+06) AND (method == 'wallet')
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.417 rec=0.417 lift= 10.9x p=2.23e-05      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=1.000 rec=0.333 lift= 52.3x p=3.05e-04      [uncertified]  (amount <= 80003) AND (settlement_utr == 'RATN27057239688')
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.8x p=1.13e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1, 1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       37/37  baseline, for comparison  -- 37 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 3004900 inside 3004900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A20_B75_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 6, 1: 5, 2: 1, 5: 8}
    narrations embedding their own reference verbatim: 14/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 31621.3
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d04_unattested_settlements                   UNDERPOWERED  single_column  settlement_report prec=1.000 rec=0.667 lift=  4.0x p=4.55e-02 LEAK [uncertified]  reported_amount <= 144374
                                                    (class size 3 of 12: even a PERFECT separator could only reach p=4.5e-03, above alpha=9.4e-05. Not certifiable clean OR leaking -- reported, not gated)
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 32.0x p=3.12e-02      [uncertified]  gstin CONTAINS '29qvaxo2672i1zf'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.500 rec=0.188 lift=  9.8x p=1.99e-03      [uncertified]  (notes['customer_segment'] == 'wholesale') AND (settled_at == 1801049400)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=0.174 rec=0.667 lift=  4.6x p=3.77e-05      [uncertified]  (amount <= 784900) AND (credit >= 519400)
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=1.000 rec=0.167 lift= 52.3x p=1.91e-02      [uncertified]  (credit >= 541804) AND (dispute_id == 'disp_eC05Xx5gZ0hf8W')
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  8.7x p=2.54e-08      [certified]  the 18 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1, 1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       36/36  baseline, for comparison  -- 36 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 1614900 inside 1614900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A20_Bnone_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days): NOT MEASURABLE -- this feed carries no settled_at, so there is no settlement date to measure a lag against. Excluded from the verdict rather than counted as constant.
    narrations embedding their own reference verbatim: 16/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 36309.4
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 31.9x p=3.14e-02      [uncertified]  order_id CONTAINS 'uveeyq1fva8yxd'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.068 rec=1.000 lift=  1.3x p=1.72e-02      [uncertified]  (description == 'Order payment') AND (dispute_id IS NULL/blank)
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.417 rec=0.417 lift= 10.9x p=2.23e-05      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.667 rec=0.333 lift= 34.9x p=9.08e-04      [uncertified]  (amount >= 9.0099e+06) AND (card_network IS NULL/blank)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.8x p=1.13e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 3/3  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, 1, 1]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       32/32  baseline, for comparison  -- 32 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 1155000 inside 1155000

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A30_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 6, 1: 5, 2: 2, 5: 7}
    narrations embedding their own reference verbatim: 17/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 13598.3
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=0.500 rec=0.182 lift= 16.8x p=4.70e-03      [uncertified]  amount CONTAINS '3750.00'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.096 rec=0.958 lift=  1.8x p=3.01e-06      [uncertified]  (amount <= 1.45e+06) AND (tax >= 504)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=0.444 rec=0.333 lift= 16.9x p=3.29e-05      [uncertified]  (amount <= 339900) AND (created_at <= 1.79939e+09)
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.667 rec=0.333 lift= 50.6x p=4.33e-04      [uncertified]  (created_at <= 1.79999e+09) AND (notes['warehouse'] == 'MAA-1')
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift= 11.4x p=2.92e-10      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=2] 3/3  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2, -2, 2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       61/61  baseline, for comparison  -- 61 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 1579900 inside 1579900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A40_B100_Cfifo

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 8, 1: 4, 2: 2, 5: 2, 6: 4}
    narrations embedding their own reference verbatim: 14/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 20842.2
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.067 lift= 32.2x p=3.11e-02      [uncertified]  order_id CONTAINS 'qqkvpqs5xq8pyq'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.073 rec=1.000 lift=  1.4x p=1.60e-05      [uncertified]  (description == 'Order payment') AND (settled == True)
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.417 rec=0.417 lift= 20.8x p=9.26e-07      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   single_column  recon   prec=1.000 rec=0.167 lift= 99.8x p=1.00e-02      [uncertified]  notes['cart_id'] == 'crt_040372'
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift= 15.0x p=1.92e-11      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2, 2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       86/86  baseline, for comparison  -- 86 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 116200 inside 116200

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A40_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 11, 1: 2, 2: 4, 5: 3}
    narrations embedding their own reference verbatim: 16/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 34055.2
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.067 lift= 32.3x p=3.10e-02      [uncertified]  gstin CONTAINS '27gipxb6711l1zf'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.103 rec=0.767 lift=  2.1x p=8.33e-06      [uncertified]  (created_at <= 1.80237e+09) AND (description == 'Order payment')
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.500 rec=0.500 lift= 25.0x p=1.29e-08      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   single_column  recon   prec=1.000 rec=0.167 lift= 99.8x p=1.00e-02      [uncertified]  notes['cart_id'] == 'crt_040459'
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift= 15.0x p=1.92e-11      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2, 2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       80/80  baseline, for comparison  -- 80 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 204700 inside 204700

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A40_B100_Crandom

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 8, 1: 4, 2: 4, 5: 4}
    narrations embedding their own reference verbatim: 15/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 12406
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.067 lift= 32.2x p=3.11e-02      [uncertified]  order_id CONTAINS 'eqdshn9u1lp5xb'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.074 rec=1.000 lift=  1.4x p=1.18e-05      [uncertified]  (description == 'Order payment') AND (settled == True)
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.333 rec=0.333 lift= 16.6x p=4.23e-05      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   single_column  recon   prec=1.000 rec=0.167 lift= 99.8x p=1.00e-02      [uncertified]  entity_id CONTAINS 'gvifsvz62g3v26'
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift= 15.0x p=1.92e-11      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2, -2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       96/96  baseline, for comparison  -- 96 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 354900 inside 354900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A40_B50_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 7, 1: 8, 2: 1, 5: 4}
    narrations embedding their own reference verbatim: 18/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 33394.6
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d04_unattested_settlements                   UNDERPOWERED  ordering       settlement_report prec=0.833 rec=0.833 lift=  1.7x p=4.00e-02      [uncertified]  the 6 lowest values of reported_reference
                                                    (class size 6 of 12: even a PERFECT separator could only reach p=1.1e-03, above alpha=1.0e-03. Not certifiable clean OR leaking -- reported, not gated)
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.067 lift= 32.2x p=3.11e-02      [uncertified]  order_id CONTAINS 'oecflycuttsarv'
  d06_payments_missing_from_erp                ok   single_column  recon   prec=0.076 rec=0.968 lift=  1.5x p=2.77e-05      [uncertified]  settled_at <= 1.80468e+09
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.417 rec=0.417 lift= 20.8x p=9.26e-07      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.500 rec=0.333 lift= 49.9x p=4.98e-04      [uncertified]  (amount >= 6.8149e+06) AND (settled_at == 1804073400)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift= 15.0x p=1.92e-11      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, 1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       79/79  baseline, for comparison  -- 79 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 1507400 inside 1507400

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A40_Bnone_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days): NOT MEASURABLE -- this feed carries no settled_at, so there is no settlement date to measure a lag against. Excluded from the verdict rather than counted as constant.
    narrations embedding their own reference verbatim: 15/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 37287.4
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.067 lift= 32.2x p=3.11e-02      [uncertified]  order_id CONTAINS 'mwgi4umbyjcnzv'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.070 rec=1.000 lift=  1.4x p=6.53e-05      [uncertified]  (created_at <= 1.8055e+09) AND (description == 'Order payment')
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.417 rec=0.417 lift= 20.8x p=9.26e-07      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   single_column  recon   prec=1.000 rec=0.167 lift= 99.8x p=1.00e-02      [uncertified]  entity_id CONTAINS 'uxra7rokfrkmbi'
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.450 rec=0.450 lift= 13.5x p=9.08e-10      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2, -2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       77/77  baseline, for comparison  -- 77 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 84900 inside 84900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets/A60_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 7, 1: 6, 2: 3, 5: 4}
    narrations embedding their own reference verbatim: 17/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 31865.1
  d03_wrong_attestation                        UNTESTABLE  (class size 1 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.045 lift= 32.3x p=3.09e-02      [uncertified]  order_id CONTAINS 'vhmt6ggxxwx2zp'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.072 rec=1.000 lift=  1.4x p=8.25e-08      [certified]  (description == 'Order payment') AND (settled == True)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=1.000 rec=0.167 lift= 73.7x p=1.69e-04      [uncertified]  (created_at >= 1.80651e+09) AND (credit >= 6.8884e+06)
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=1.000 rec=0.333 lift=147.3x p=3.84e-05      [uncertified]  (amount >= 9.38799e+06) AND (created_at >= 1.80622e+09)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.450 rec=0.450 lift= 19.9x p=2.85e-11      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, -1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       133/133  baseline, for comparison  -- 133 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 156200 inside 156200

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A10_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 9, 1: 4, 2: 3, 5: 1, 6: 3}
    narrations embedding their own reference verbatim: 13/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.700 rec=1.000 lift=  2.0x p=1.55e-03      [uncertified]  amount <= 39200.3
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.250 lift= 35.0x p=2.86e-02      [uncertified]  order_id CONTAINS '8bi8kggayjxkio'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.667 rec=0.200 lift= 11.5x p=8.79e-03      [uncertified]  (notes['warehouse'] == '*') AND (settled_at == 1803468600)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=1.000 rec=0.167 lift= 14.4x p=4.44e-03      [uncertified]  (amount >= 7.0099e+06) AND (notes['warehouse'] == 'MAA-1')
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.273 rec=1.000 lift=  7.9x p=2.19e-06      [uncertified]  (created_at <= 1.79957e+09) AND (description == 'Order payment')
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.550 rec=0.550 lift=  4.8x p=2.32e-07      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=2] 3/3  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2, 2, 2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       21/21  baseline, for comparison  -- 21 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 3804900 inside 3804900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A20_B0_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 8, 1: 4, 2: 3, 5: 5}
    narrations embedding their own reference verbatim: 18/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 26811.6
  d04_unattested_settlements                   UNTESTABLE  (class size 12 < 3) DEGENERATE: the class is 12/12 of the table, so it cannot be separated FROM it -- it IS it
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 31.9x p=3.14e-02      [uncertified]  order_id CONTAINS 'gv5e6aqtakxlel'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.364 rec=0.235 lift=  6.7x p=1.56e-03      [uncertified]  (credit <= 292822) AND (settled_at == 1804073400)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=1.000 rec=0.167 lift= 26.2x p=1.34e-03      [uncertified]  (amount <= 40000) AND (card_network == 'MasterCard')
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.500 rec=0.333 lift= 26.2x p=1.80e-03      [uncertified]  (fee >= 33326) AND (settled_at == 1803468600)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.8x p=1.13e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, 1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       33/33  baseline, for comparison  -- 33 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 449900 inside 449900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A20_B100_Cfifo

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 4, 1: 3, 2: 4, 5: 8, 6: 1}
    narrations embedding their own reference verbatim: 16/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 38878
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 32.0x p=3.12e-02      [uncertified]  order_id CONTAINS 'ppfzubtzw6gpjb'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.667 rec=0.125 lift= 13.1x p=7.11e-03      [uncertified]  (card_network == 'Amex') AND (notes['warehouse'] == 'BLR-2')
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.417 rec=0.417 lift= 10.9x p=2.23e-05      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=1.000 rec=0.333 lift= 52.3x p=3.05e-04      [uncertified]  (amount >= 7.8049e+06) AND (settled_at == 1802863800)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.579 rec=0.579 lift=  9.6x p=7.63e-11      [certified]  the 19 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2, -2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       33/33  baseline, for comparison  -- 33 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 63300 inside 63300

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A20_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 9, 1: 4, 5: 6, 6: 1}
    narrations embedding their own reference verbatim: 13/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 39067.7
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=0.667 rec=0.250 lift= 21.3x p=2.53e-03      [uncertified]  amount CONTAINS '15400.00'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=1.000 rec=0.125 lift= 19.6x p=2.44e-03      [uncertified]  (amount >= 3.2149e+06) AND (notes['customer_segment'] == 'marketplace')
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=0.800 rec=0.333 lift= 20.9x p=6.10e-06      [uncertified]  (created_at >= 1.8061e+09) AND (credit >= 1.65002e+06)
  d07_decoy_credit_near_collision              ok   single_column  recon   prec=1.000 rec=0.167 lift= 52.3x p=1.91e-02      [uncertified]  notes['cart_id'] == 'crt_040061'
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.8x p=1.13e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2, 2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       31/31  baseline, for comparison  -- 31 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 168300 inside 168300

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A20_B100_Crandom

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 7, 1: 8, 2: 1, 5: 4}
    narrations embedding their own reference verbatim: 16/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 20654.2
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 31.9x p=3.14e-02      [uncertified]  order_id CONTAINS '05k2ubsrdyzrwf'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.500 rec=0.176 lift=  9.2x p=2.40e-03      [uncertified]  (method == 'netbanking') AND (settled_at == 1805887800)
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.364 rec=0.364 lift= 10.4x p=2.41e-04      [certified]  the 11 highest values of order_id
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.667 rec=0.333 lift= 34.9x p=9.08e-04      [uncertified]  (created_at >= 1.80624e+09) AND (credit >= 1.42554e+06)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift=  7.8x p=1.13e-08      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, -1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       40/40  baseline, for comparison  -- 40 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 1936600 inside 1936600

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A20_B100_Crandom0

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 4, 1: 5, 2: 5, 5: 6}
    narrations embedding their own reference verbatim: 14/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 35682.6
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 31.9x p=3.14e-02      [uncertified]  order_id CONTAINS '40fcpphkpl2lj6'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=1.000 rec=0.118 lift= 18.5x p=2.77e-03      [uncertified]  (card_network == 'RuPay') AND (settled_at == 1805887800)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=0.364 rec=0.333 lift=  9.5x p=3.55e-04      [uncertified]  (created_at >= 1.80614e+09) AND (credit >= 439087)
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.667 rec=0.333 lift= 34.9x p=9.08e-04      [uncertified]  (amount <= 70004) AND (created_at >= 1.80618e+09)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.421 rec=0.421 lift=  7.0x p=1.86e-06      [certified]  the 19 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=2] 3/3  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2, 2, 2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       37/37  baseline, for comparison  -- 37 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 275000 inside 275000

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A20_B50_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 6, 1: 7, 2: 1, 5: 6}
    narrations embedding their own reference verbatim: 16/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 38768.1
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d04_unattested_settlements                   UNDERPOWERED  ordering       settlement_report prec=0.833 rec=0.833 lift=  1.7x p=4.00e-02      [uncertified]  the 6 lowest values of settlement_id
                                                    (class size 6 of 12: even a PERFECT separator could only reach p=1.1e-03, above alpha=1.0e-03. Not certifiable clean OR leaking -- reported, not gated)
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 31.9x p=3.14e-02      [uncertified]  order_id CONTAINS 'q2oxkaqnqm2pcc'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=1.000 rec=0.118 lift= 18.5x p=2.77e-03      [uncertified]  (card_type == 'debit') AND (notes['warehouse'] == 'HYD-1')
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=0.600 rec=0.500 lift= 15.7x p=1.43e-07      [certified]  (created_at <= 1.79927e+09) AND (settled_at == 1799839800)
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.571 rec=0.667 lift= 29.9x p=1.30e-06      [uncertified]  (amount >= 5.7099e+06) AND (created_at >= 1.80546e+09)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.450 rec=0.450 lift=  7.1x p=2.68e-07      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, -1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       39/39  baseline, for comparison  -- 39 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 721600 inside 721600

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A20_B75_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 5, 1: 7, 2: 4, 5: 3, 6: 1}
    narrations embedding their own reference verbatim: 15/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 38251.1
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d04_unattested_settlements                   UNDERPOWERED  single_column  settlement_report prec=0.500 rec=1.000 lift=  2.0x p=9.09e-02      [uncertified]  reported_amount <= 269792
                                                    (class size 3 of 12: even a PERFECT separator could only reach p=4.5e-03, above alpha=9.3e-05. Not certifiable clean OR leaking -- reported, not gated)
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.125 lift= 32.0x p=3.12e-02      [uncertified]  gstin CONTAINS '27rbaxl6318d1z2'
  d06_payments_missing_from_erp                ok   single_column  recon   prec=0.093 rec=1.000 lift=  1.8x p=4.72e-05      [uncertified]  tax >= 1493
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=0.800 rec=0.333 lift= 20.9x p=6.10e-06      [uncertified]  (amount <= 225000) AND (credit >= 209633)
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.667 rec=0.333 lift= 34.9x p=9.08e-04      [uncertified]  (amount >= 4.3549e+06) AND (created_at <= 1.79934e+09)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.550 rec=0.550 lift=  8.6x p=3.57e-10      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [-1, 1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       37/37  baseline, for comparison  -- 37 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 609900 inside 609900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A30_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 6, 1: 6, 2: 3, 5: 4, 6: 1}
    narrations embedding their own reference verbatim: 17/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 34921.6
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.091 lift= 33.5x p=2.98e-02      [uncertified]  order_id CONTAINS 'wj5wr201rxufo4'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=1.000 rec=0.083 lift= 19.0x p=2.67e-03      [uncertified]  (fee >= 218061) AND (settled_at >= 1.80468e+09)
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.333 rec=0.333 lift= 12.6x p=1.24e-04      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   single_column  recon   prec=1.000 rec=0.167 lift= 75.8x p=1.32e-02      [uncertified]  notes['cart_id'] == 'crt_049456'
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.550 rec=0.550 lift= 12.5x p=6.20e-12      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, -1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       59/59  baseline, for comparison  -- 59 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 741900 inside 741900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A40_B100_Cfifo

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 5, 1: 5, 2: 2, 5: 7, 6: 1}
    narrations embedding their own reference verbatim: 15/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 36685.3
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.067 lift= 32.3x p=3.10e-02      [uncertified]  order_id CONTAINS 'qvpj6aadxyhp9j'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.072 rec=1.000 lift=  1.4x p=1.59e-05      [uncertified]  (description == 'Order payment') AND (settled == True)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=1.000 rec=0.167 lift= 49.9x p=3.69e-04      [uncertified]  (amount >= 7.0149e+06) AND (notes['warehouse'] == 'MAA-1')
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=1.000 rec=0.333 lift= 99.8x p=8.38e-05      [uncertified]  (amount >= 7.5049e+06) AND (settled_at == 1803468600)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift= 15.0x p=1.92e-11      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, -1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       77/77  baseline, for comparison  -- 77 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 580000 inside 580000

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A40_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 4, 1: 7, 2: 3, 5: 6}
    narrations embedding their own reference verbatim: 15/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.778 rec=1.000 lift=  2.2x p=4.64e-04      [uncertified]  amount <= 31546.8
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=0.500 rec=0.133 lift= 16.1x p=5.22e-03      [uncertified]  amount CONTAINS '23549.00'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.073 rec=1.000 lift=  1.4x p=2.00e-05      [uncertified]  (description == 'Order payment') AND (settled == True)
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.417 rec=0.417 lift= 20.8x p=9.26e-07      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.667 rec=0.333 lift= 66.6x p=2.50e-04      [uncertified]  (created_at >= 1.80561e+09) AND (notes['warehouse'] == 'MAA-1')
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.450 rec=0.450 lift= 13.5x p=9.08e-10      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, 1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       79/79  baseline, for comparison  -- 79 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 48000 inside 48000

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A40_B100_Crandom

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 19
    posting lag (days) distribution: {0: 9, 1: 2, 2: 2, 5: 4, 6: 2}
    narrations embedding their own reference verbatim: 15/19   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.4x p=1.59e-04      [uncertified]  amount <= 17185
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   column_pair    erp     prec=1.000 rec=0.133 lift= 32.1x p=9.06e-04      [uncertified]  (amount CONTAINS '6199.00') AND (gstin IS NULL/blank)
  d06_payments_missing_from_erp                ok   single_column  recon   prec=0.074 rec=1.000 lift=  1.4x p=2.22e-05      [uncertified]  fee >= 4012
  d07_decoy_credit_collision                   ok   ordering       recon   prec=0.333 rec=0.333 lift= 16.6x p=4.23e-05      [certified]  the 12 highest values of order_receipt
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=0.333 rec=0.333 lift= 33.3x p=1.23e-03      [uncertified]  (amount >= 7.2049e+06) AND (settled_at == 1805283000)
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.450 rec=0.450 lift= 13.5x p=9.08e-10      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2, 2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       73/73  baseline, for comparison  -- 73 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 424900 inside 424900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A40_B50_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 9, 1: 2, 2: 6, 5: 2, 6: 1}
    narrations embedding their own reference verbatim: 17/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 34705.1
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d04_unattested_settlements                   UNDERPOWERED  ordering       settlement_report prec=0.667 rec=0.667 lift=  1.3x p=2.84e-01      [uncertified]  the 6 lowest values of settlement_id
                                                    (class size 6 of 12: even a PERFECT separator could only reach p=1.1e-03, above alpha=1.0e-03. Not certifiable clean OR leaking -- reported, not gated)
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.067 lift= 32.3x p=3.10e-02      [uncertified]  order_id CONTAINS 'es9wxdvythonbj'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.072 rec=1.000 lift=  1.4x p=1.27e-05      [uncertified]  (description == 'Order payment') AND (settled == True)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=0.800 rec=0.333 lift= 39.9x p=4.61e-07      [certified]  (amount <= 74900) AND (settlement_utr == 'RATN27041214572')
  d07_decoy_credit_near_collision              ok   single_column  recon   prec=1.000 rec=0.167 lift= 99.8x p=1.00e-02      [uncertified]  notes['cart_id'] == 'crt_042580'
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift= 15.0x p=1.92e-11      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 2/2  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1, 1]
    ok   d07_decoy_credit_near_collision[delta=2] 1/1  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       84/84  baseline, for comparison  -- 84 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 1112900 inside 1112900

## VERDICT: PASS


# LEAKAGE AUDIT -- /Users/deva/razorpay/corpus/datasets_v2/A60_B100_Cmax

thresholds: precision >= 0.9, recall >= 0.5, Bonferroni-corrected alpha = 0.01 / hypotheses

## Bank independence

    bank lines: 20
    posting lag (days) distribution: {0: 8, 1: 3, 2: 1, 5: 4, 6: 4}
    narrations embedding their own reference verbatim: 14/20   (not a leak by itself -- see `reference_derivable`)
    VERDICT: bank is INDEPENDENT

## Per-class strongest separator

  d01_settlement_reversal                      UNTESTABLE  (class size 1 < 3) 
  d02_foreign_bank_lines                       ok   single_column  bank    prec=0.875 rec=1.000 lift=  2.5x p=1.03e-04      [uncertified]  amount <= 39280.6
  d03_wrong_attestation                        UNTESTABLE  (class size 2 < 3) 
  d05_erp_orphan_invoices                      ok   single_column  erp     prec=1.000 rec=0.045 lift= 32.3x p=3.10e-02      [uncertified]  order_id CONTAINS 'jia36wthmwn9ho'
  d06_payments_missing_from_erp                ok   column_pair    recon   prec=0.071 rec=0.978 lift=  1.4x p=3.83e-06      [uncertified]  (description == 'Order payment') AND (settled == True)
  d07_decoy_credit_collision                   ok   column_pair    recon   prec=1.000 rec=0.167 lift= 73.7x p=1.69e-04      [uncertified]  (amount >= 9.57839e+06) AND (settled_at == 1805887800)
  d07_decoy_credit_near_collision              ok   column_pair    recon   prec=1.000 rec=0.167 lift=147.3x p=6.79e-03      [uncertified]  (amount >= 1.6899e+06) AND (order_id CONTAINS '3tvnchkbz6m4xr')
  d08_duplicate_payment_rows                   ok   ordering       recon   prec=0.500 rec=0.500 lift= 22.1x p=4.03e-13      [certified]  the 20 highest values of order_receipt
  d09_itc_at_risk                              UNTESTABLE  (class size 2 < 3) 
  d11_false_settlement_id                      UNTESTABLE  (class size 0 < 3) 

## Class efficacy -- did the class do what it claims?

    ok   d07_decoy_credit_collision         6/6  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   d07_decoy_credit_near_collision[delta=1] 1/1  pairs differ on `credit` by exactly 1 paise  -- observed credit deltas [1]
    ok   d07_decoy_credit_near_collision[delta=2] 2/2  pairs differ on `credit` by exactly 2 paise  -- observed credit deltas [-2, -2]
    ok   d08_duplicate_payment_rows         10/10  pairs collide on `credit` (delta 0)  -- observed credit deltas [0, 0, 0, 0, 0, 0]
    ok   incidental_credit_collisions       127/127  baseline, for comparison  -- 127 credit values shared by 2+ payments

## Derivable fields

    derivability   debit = contains amount verbatim [100.0% of rows]  e.g. 744900 inside 744900

## VERDICT: PASS

