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

