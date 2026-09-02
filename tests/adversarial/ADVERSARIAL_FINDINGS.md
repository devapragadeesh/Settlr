# ADVERSARIAL FINDINGS — malformed-input robustness of `resolver/` and `matching/`

**Generated entirely by `tests/adversarial/run_adversarial.py`. No number below is hand-typed.**

Governing decision: `DECISIONS.md` 52. Both packages are exercised read-only through their public `load()` + resolve/cascade entry point on single-field or single-file corruptions of one minimal, valid dataset (`corpus/datasets/A10_B100_Cmax`, cloned per case, never written to). Every outcome is sorted into exactly one of three buckets:

1. **clean, typed decline** — best outcome.
2. **uncaught low-level exception** — allowed; the type is recorded so a change in which exception fires is visible.
3. **silent, plausible-looking wrong answer** — a `Verified`/`Determinate` built from corrupted input with no signal anything was off. The only bucket that fails `pytest tests/adversarial -q`.

## resolver — 22 cases run

| bucket | count |
|---|---:|
| 1 (clean typed decline) | 8 |
| 2 (uncaught exception) | 14 |
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
| bank.missing_header_column | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | 2 (KeyError) | raised while loading (matching.loaders.load) |
| bank.blank_value_date | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | 2 (ValueError) | raised while loading (matching.loaders.load) |
| bank.non_numeric_amount | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | 2 (ValueError) | raised while loading (matching.loaders.load) |
| bank.duplicate_bank_reference | 1 (-) | bank[1] resolved AttestationDiscrepancy -- not a confident Verified | 1 (-) | bank[1] resolved Unresolved -- not a confident Determinate |
| bank.zero_row_file | 2 (ValueError) | ValueError raised while resolving (resolver.resolve.resolve) | 2 (ValueError) | raised while running the cascade (matching.cascade.run) |
| bank.only_foreign_lines | 1 (-) | load()+resolve() completed; the corrupted surface does not feed Verified's arithmetic (see cases.py for why), so no bucket-3 check applies here | 1 (-) | load()+cascade completed; the corrupted surface does not feed Determinate's arithmetic (see cases.py for why), so no bucket-3 check applies here |
| bank.over_precision_amount | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | 2 (ValueError) | raised while loading (matching.loaders.load) |
| settlement_report.duplicate_settlement_id | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | n/a |  |
| settlement_report.missing_reported_amount_column | 2 (KeyError) | KeyError raised while loading (resolver.loaders.load) | n/a |  |
| settlement_report.non_numeric_amount | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | n/a |  |
| disputes.malformed_shape | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | 2 (KeyError) | raised while loading (matching.loaders.load) |
| disputes.missing_id | 2 (ValueError) | ValueError raised while loading (resolver.loaders.load) | 1 (-) | load()+cascade completed; the corrupted surface does not feed Determinate's arithmetic (see cases.py for why), so no bucket-3 check applies here |

---

## Bucket-3 findings: none

No case, on either package, produced a confident `Verified`/`Determinate` from corrupted input. This is a valid, reportable outcome in its own right, not an absence of testing -- see the full case table above for exactly what was tried.

---

## Additional observations (not part of the 3-bucket tally)

Behaviours the case sweep surfaced that are real but do not fit the Verified/Determinate bucket-3 definition -- recorded here rather than silently folded into bucket 1.

**All four are now CLOSED (2026-09-03).** Each bullet is kept, rewritten, rather than deleted: what the defect was, what it would have cost, and the test that now pins the fixed behaviour. A section that empties itself as findings are fixed loses the record that they were ever found, and the tests named below were, until this date, asserting that three of these four defects PERSISTED.

- **The two `paise` parsers agree. FIXED 2026-09-03; the finding this bullet used to report is closed.** Both parse the same kind of rupee-string cell. `resolver.loaders.paise` previously did unchecked string surgery, `int((frac + "00")[:2])`, silently dropping any digits past the second -- `"7612.9951"` became `761299` paise with no signal -- while `matching.money.paise` raised `ValueError` on the identical cell. Both now enforce `^(-?)(\d+)(?:\.(\d{1,2}))?$` and reject it. The grammar is duplicated rather than shared because `resolver/` may not import `matching/` (`resolver/tests/test_isolation.py`). Behaviour-preserving on every dataset in the repo: 6,374 money cells across 168 CSVs, zero rejected. See `test_malformed_bank.py::test_the_two_paise_parsers_agree` and `::test_over_precision_is_rejected_not_truncated`.
- **`resolver.loaders.load` refused a duplicate `settlement_id`. FIXED 2026-09-03; the finding this bullet used to report is closed.** The `settlement_report` dict was built by plain assignment in file order, so a repeated `settlement_id` silently OVERWROTE the earlier row -- last-write-wins, no error, no signal. That feed is the PSP's attestation, so discarding one of two contradicting claims was the worst available answer to a self-contradicting record. It now raises `ValueError`. See `test_malformed_settlement_report.py::test_duplicate_settlement_id_is_refused_not_overwritten`.
- **An unrecognised `disputes.json` shape no longer empties the dispute set. FIXED 2026-09-03.** `payload.get("items", payload if isinstance(payload, list) else [])` fell through to `[]` for a plain JSON object that was neither `{"items": [...]}` nor a bare array, so "no disputes exist" and "this shape is unrecognised" were indistinguishable. `resolver.loaders._load_disputes` now dispatches on shape explicitly and raises `ValueError`. `matching.loaders.load` raises `KeyError` on the same file; `matching/` is frozen and unchanged, so the two packages now agree the file is malformed and differ only in which exception says so. See `test_malformed_erp_disputes.py::test_resolver_refuses_the_unhandled_shape`.
- **A dispute item with no usable id no longer collapses to key `""`. FIXED 2026-09-03.** `item.get("id") or item.get("dispute_id", "")` mapped every such item to `""`, and a second one overwrote the first. That key was not inert: `resolver/breaks.py` reads back with `disputes.get(row.get("dispute_id") or "")`, so every payment row without a `dispute_id` -- 94% of recon rows -- probed `""` as well, and one malformed item would have reclassified almost the entire non-disputed population as `UNEXPECTED_CHANGE`. The loader now refuses the item, and refuses a duplicate dispute id. See `test_malformed_erp_disputes.py::test_dispute_missing_id_is_refused_not_collapsed_to_one_key` and `::test_a_duplicate_dispute_id_is_refused`.

