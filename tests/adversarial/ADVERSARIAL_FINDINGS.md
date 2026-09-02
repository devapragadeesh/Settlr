# ADVERSARIAL FINDINGS — malformed-input robustness of `resolver/` and `matching/`

**Generated entirely by `tests/adversarial/run_adversarial.py`. No number below is hand-typed.**

Governing decision: `DECISIONS.md` 52. Both packages are exercised read-only through their public `load()` + resolve/cascade entry point on single-field or single-file corruptions of one minimal, valid dataset (`corpus/datasets/A10_B100_Cmax`, cloned per case, never written to). Every outcome is sorted into exactly one of three buckets:

1. **clean, typed decline** — best outcome.
2. **uncaught low-level exception** — allowed; the type is recorded so a change in which exception fires is visible.
3. **silent, plausible-looking wrong answer** — a `Verified`/`Determinate` built from corrupted input with no signal anything was off. The only bucket that fails `pytest tests/adversarial -q`.

## resolver — 22 cases run

| bucket | count |
|---|---:|
| 1 (clean typed decline) | 12 |
| 2 (uncaught exception) | 10 |
| 3 (SILENT WRONG ANSWER) | 0 |

## matching — 18 cases run

| bucket | count |
|---|---:|
| 1 (clean typed decline) | 7 |
| 2 (uncaught exception) | 11 |
| 3 (SILENT WRONG ANSWER) | 0 |

---

## Full case table

| surface.case | resolver bucket | resolver detail | matching bucket | matching detail |
|---|---|---|---|---|
| recon.truncated_json | 2 (JSONDecodeError) | JSONDecodeError raised while loading (resolver.loaders.load) | 2 (JSONDecodeError) | raised while loading (matching.loaders.load) |
| recon.missing_items_key | 2 (KeyError) | KeyError raised while loading (resolver.loaders.load) | 2 (KeyError) | raised while loading (matching.loaders.load) |
| recon.empty_items_array | 1 (-) | resolve() completed with 20 line outcome(s), none Verified | 1 (-) | cascade completed with 20 reconstruction(s), none Determinate |
| recon.duplicate_entity_id | 1 (ContractViolation) | ContractViolation raised by resolver.resolve.resolve -- a package-defined typed decline | 1 (BalanceViolation) | BalanceViolation raised by matching.cascade.run -- a package-defined typed decline |
| recon.negative_amount | 1 (-) | bank[0] resolved AttestationDiscrepancy -- not a confident Verified | 1 (-) | bank[0] resolved Unresolved -- not a confident Determinate |
| recon.out_of_order_created_at | 1 (-) | bank[0] resolved AttestationDiscrepancy -- not a confident Verified | 1 (-) | bank[0] resolved Unresolved -- not a confident Determinate |
| recon.settlement_id_null | 1 (-) | bank[0] resolved AttestationDiscrepancy -- not a confident Verified | n/a |  |
| recon.settlement_id_absent | 1 (-) | bank[0] resolved AttestationDiscrepancy -- not a confident Verified | 2 (KeyError) | raised while running the cascade (matching.cascade.run) |
| recon.non_numeric_amount | 2 (TypeError) | TypeError raised while resolving (resolver.resolve.resolve) | 2 (TypeError) | raised while running the cascade (matching.cascade.run) |
| recon.over_precision_amount | 2 (TypeError) | TypeError raised while resolving (resolver.resolve.resolve) | 2 (TypeError) | raised while running the cascade (matching.cascade.run) |
| bank.missing_header_column | 2 (KeyError) | KeyError raised while loading (resolver.loaders.load) | 2 (KeyError) | raised while loading (matching.loaders.load) |
| bank.blank_value_date | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | 2 (ValueError) | raised while loading (matching.loaders.load) |
| bank.non_numeric_amount | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | 2 (ValueError) | raised while loading (matching.loaders.load) |
| bank.duplicate_bank_reference | 1 (-) | bank[1] resolved AttestationDiscrepancy -- not a confident Verified | 1 (-) | bank[1] resolved Unresolved -- not a confident Determinate |
| bank.zero_row_file | 2 (ValueError) | ValueError raised while resolving (resolver.resolve.resolve) | 2 (ValueError) | raised while running the cascade (matching.cascade.run) |
| bank.only_foreign_lines | 1 (-) | load()+resolve() completed; the corrupted surface does not feed Verified's arithmetic (see cases.py for why), so no bucket-3 check applies here | 1 (-) | load()+cascade completed; the corrupted surface does not feed Determinate's arithmetic (see cases.py for why), so no bucket-3 check applies here |
| bank.over_precision_amount | 1 (-) | load()+resolve() completed; the corrupted surface does not feed Verified's arithmetic (see cases.py for why), so no bucket-3 check applies here | 2 (ValueError) | raised while loading (matching.loaders.load) |
| settlement_report.duplicate_settlement_id | 1 (-) | bank[0] resolved AttestationDiscrepancy -- not a confident Verified | n/a |  |
| settlement_report.missing_reported_amount_column | 2 (KeyError) | KeyError raised while loading (resolver.loaders.load) | n/a |  |
| settlement_report.non_numeric_amount | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | n/a |  |
| disputes.malformed_shape | 1 (-) | load()+resolve() completed; the corrupted surface does not feed Verified's arithmetic (see cases.py for why), so no bucket-3 check applies here | 2 (KeyError) | raised while loading (matching.loaders.load) |
| disputes.missing_id | 1 (-) | load()+resolve() completed; the corrupted surface does not feed Verified's arithmetic (see cases.py for why), so no bucket-3 check applies here | 1 (-) | load()+cascade completed; the corrupted surface does not feed Determinate's arithmetic (see cases.py for why), so no bucket-3 check applies here |

---

## Bucket-3 findings: none

No case, on either package, produced a confident `Verified`/`Determinate` from corrupted input. This is a valid, reportable outcome in its own right, not an absence of testing -- see the full case table above for exactly what was tried.

---

## Additional observations (not part of the 3-bucket tally)

These are behaviours the case sweep surfaced that are real but do not fit the Verified/Determinate bucket-3 definition -- documented here rather than silently folded into bucket 1.

- **`resolver.loaders.paise` truncates, `matching.money.paise` rejects.** Both parse the same kind of rupee-string cell. `matching.money.paise` matches `^(-?)(\d+)(?:\.(\d{1,2}))?$` and raises `ValueError` on a third decimal digit. `resolver.loaders.paise` does unchecked string surgery, `int((frac + "00")[:2])`, and silently drops any digits past the second -- `"7612.9951"` becomes `761299` paise with no signal. See `test_malformed_bank.py::test_paise_truncate_vs_reject_over_precision`.
- **`resolver.loaders.load`'s `settlement_report` dict is last-write-wins on a duplicate `settlement_id`**, silently. See `test_malformed_settlement_report.py::test_duplicate_settlement_id_is_last_write_wins_in_the_loader`.
- **A `disputes.json` shaped as a plain object (not `{"items": [...]}`, not a bare array) silently empties `resolver`'s dispute set** (`payload.get("items", ...)` falls through to `[]`), while the same file makes `matching.loaders.load` raise `KeyError` on `["items"]`. See `test_malformed_erp_disputes.py`.
- **A dispute item missing both `id` and `dispute_id` maps to key `""`** in `resolver`'s disputes dict (`item.get("id") or item.get("dispute_id", "")`); a second such item would silently overwrite the first. Not exercised at two-item scale here, since that is a two-row mutation and this suite corrupts one field at a time.

