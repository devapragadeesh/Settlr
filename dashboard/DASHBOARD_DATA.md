# DASHBOARD_DATA — every field, its source, its denominator, its scope

Generated data lives at `dashboard/data.json`, written by `corpus/export_dashboard.py`.
Same discipline as `CLAIMS.md`: if a number below cannot be traced to a generating artefact,
it does not ship, and the dashboard screen that would have used it is wrong, not empty-filled.

`corpus/tests/test_dashboard_export.py` asserts every field listed as "computed" here still
matches its source exactly; it is watched to fail (confirmed: injecting a fabricated claim
or a fabricated `self_correction_record.count` both make it fail, naming the exact
assertion).

| `data.json` field | source artefact / owning function | denominator | scope |
|---|---|---|---|
| `claims` | `corpus.claims_ledger.rows()`, reused directly (not re-derived) | each row states its own, e.g. "of 275 `Verified`" | 30 datasets, all rows |
| `coverage.all` | `corpus.coverage.split(oracle_results, "all")` | 359 settlement lines | all 30 datasets |
| `coverage.non_absence` | same function, scope `non_absence` | 335 settlement lines | 28 datasets carrying a PSP artefact |
| `coverage.absence` | same function, scope `absence` | 24 settlement lines | the 2 PSP-absence datasets |
| `coverage.original_14` | same function, scope `original_14` | 168 settlement lines | the scope `THREE_SYSTEMS.md` publishes |
| `three_systems.per_dataset[].naive` | `corpus.three_systems.naive_row()`, reused directly | per row, e.g. "of 12 compositions attempted" | per dataset |
| `three_systems.per_dataset[].frozen` | `corpus.three_systems.frozen_row()`, reading `corpus/baseline_results.json` | per row | per dataset; `"cannot run"` at the 2 PSP-absence points |
| `three_systems.per_dataset[].resolver` | `corpus.three_systems.resolver_row()`, reading `corpus/oracle_results.json` | per row | per dataset |
| `d15` | `corpus.scorecard.D15` — a held constant, sourced from `investigation/D15_MEASUREMENT.md`'s one-time enumeration | 18 reconstructible instances | the 2 PSP-absence datasets |
| `hashes.primary_dataset` | live `shasum -a 256 -c` against `engine/DATASET_HASHES.txt` | 6 files | the frozen primary dataset |
| `hashes.corpus_datasets` | live `shasum -a 256 -c` against every `corpus/datasets*/*/DATASET_HASHES.txt` | 30 manifests | all 30 corpus datasets |
| `commit_ordering` | live `git log --reverse`, this checkout | all commits in this repo | the whole history, not a curated subset |
| `self_correction_record` | **not a number** — see below | n/a | n/a |
| `not_available` | computed by `export_dashboard.py` itself, from whether `oracle_results.json`/`baseline_results.json` exist | n/a | whichever prerequisite artefacts are missing |

## The one field deliberately NOT a number

`self_correction_record` is a citation object (`{"available_as_number": false, "citation":
"DECISIONS.md §44.4"}`), not a count. `DECISIONS.md` §44.4 records four instances of this
project finding the error it had just catalogued — but "how many times has this happened" is
a narrative pattern in prose, not a quantity any script computes, and inventing a script to
count paragraph headers matching a pattern would be exactly the kind of ungrounded number
this project exists to refuse. The Integrity screen must render this field as a link to the
document, never as a statistic. `corpus/tests/test_dashboard_export.py::
test_export_invents_no_field_the_repo_does_not_own` enforces this — it fails if a `count`
key ever appears on this object.

## Screens this data can honestly support, and screens it cannot yet

**Can support now, fully from `data.json`:** a coverage overview (the three-way split,
correctly separating `record_contradicted` from `not_determinable`), a three-systems
comparison table (naive / frozen / resolver, per dataset and aggregable), the D15 finding as
a fixed, cited number, live hash-verification status, and the commit-ordering evidence as an
Integrity screen.

**Cannot yet be supported without inventing data, and are deliberately left out of this
export:** a Sankey money-flow view (no artefact here traces individual payment rows through
PSP → settlement → bank credit → ERP/GST in one place — that would need a new, dedicated
per-transaction join this export does not attempt); a Settlement Explorer showing full
per-line evidence and audit timelines (the per-dataset records in `oracle_results.json` are
aggregate counts, not the row-level `Resolution` objects a per-credit drill-down needs); an
Exceptions/Open-Breaks queue clustered by causing line (the counts exist in `measured.
open_break`, but the per-row cluster assignments do not survive into the oracle's aggregate
output). Building any of these honestly requires either a new export field sourced from a
script that does not yet exist, or reading `resolver/` output directly and writing the
missing owning function first — not stitching one together inside the export layer, which
would violate this module's own rule against computing what nothing else owns.
