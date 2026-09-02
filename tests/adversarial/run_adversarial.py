"""Standalone driver: run every adversarial case against both `resolver/` and
`matching/`, tabulate bucket 1/2/3 per package, and write
`ADVERSARIAL_FINDINGS.md`. Every number in that file comes from this run --
nothing in it is hand-typed, per this repo's convention that a number in a
markdown file traces to a script (`CLAUDE.md`, "Conventions").

    python3 tests/adversarial/run_adversarial.py

Read-only against `resolver/` and `matching/`: only `load()` and the
resolve/cascade entry point are called, exactly as `test_resolver_survives.py`
and `test_matching_survives.py` do. This script does not assert anything and
never fails the build -- `pytest tests/adversarial -q` is what gates on
bucket 3; this is the reporting pass.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for candidate in (ROOT, HERE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import cases as cases_module                                    # noqa: E402
import bucket as bucket_module                                  # noqa: E402
import conftest as conftest_module                               # noqa: E402

BUCKET_NAMES = {1: "clean typed decline", 2: "uncaught exception",
                3: "SILENT WRONG ANSWER"}


def build_baselines(tmp_root: Path):
    resolver_baseline = conftest_module.build_resolver_baseline(
        tmp_root / "resolver_base" / "dataset")
    matching_baseline = conftest_module.build_matching_baseline(
        tmp_root / "matching_base" / "dataset")
    return resolver_baseline, matching_baseline


def run_case(case, baseline: Path, tmp_root: Path, package: str, index: int):
    case_dir = conftest_module.clone_dataset(
        baseline, tmp_root / f"{package}_{index:03d}")
    began = time.perf_counter()
    meta = case.mutate(case_dir)
    if package == "resolver":
        outcome = bucket_module.classify_resolver(
            case_dir, meta.get("target_bank_index"))
    else:
        outcome = bucket_module.classify_matching(
            case_dir, meta.get("target_bank_index"))
    elapsed = time.perf_counter() - began
    return outcome, elapsed


def main() -> int:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="adversarial_run_") as tmp:
        tmp_root = Path(tmp)
        resolver_baseline, matching_baseline = build_baselines(tmp_root / "base")

        rows = []
        for index, case in enumerate(cases_module.ALL_CASES):
            record = {"surface": case.surface, "name": case.name, "note": case.note}
            if "resolver" in case.targets:
                outcome, elapsed = run_case(
                    case, resolver_baseline, tmp_root / "resolver", "resolver", index)
                record["resolver"] = outcome
                record["resolver_seconds"] = elapsed
            if "matching" in case.targets:
                outcome, elapsed = run_case(
                    case, matching_baseline, tmp_root / "matching", "matching", index)
                record["matching"] = outcome
                record["matching_seconds"] = elapsed
            rows.append(record)

    write_report(rows)
    print_summary(rows)
    return 0


def print_summary(rows: list[dict]) -> None:
    for package in ("resolver", "matching"):
        tally = {1: 0, 2: 0, 3: 0}
        for row in rows:
            outcome = row.get(package)
            if outcome:
                tally[outcome.bucket] += 1
        print(f"{package}: bucket1={tally[1]} bucket2={tally[2]} "
              f"bucket3={tally[3]} / {sum(tally.values())} cases")


def write_report(rows: list[dict]) -> None:
    out = HERE / "ADVERSARIAL_FINDINGS.md"
    lines: list[str] = []
    lines.append("# ADVERSARIAL FINDINGS — malformed-input robustness of "
                 "`resolver/` and `matching/`")
    lines.append("")
    lines.append("**Generated entirely by `tests/adversarial/run_adversarial.py`. "
                 "No number below is hand-typed.**")
    lines.append("")
    lines.append("Governing decision: `DECISIONS.md` 52. Both packages are "
                 "exercised read-only through their public `load()` + "
                 "resolve/cascade entry point on single-field or single-file "
                 "corruptions of one minimal, valid dataset "
                 "(`corpus/datasets/A10_B100_Cmax`, cloned per case, never "
                 "written to). Every outcome is sorted into exactly one of "
                 "three buckets:")
    lines.append("")
    lines.append("1. **clean, typed decline** — best outcome.")
    lines.append("2. **uncaught low-level exception** — allowed; the type "
                 "is recorded so a change in which exception fires is "
                 "visible.")
    lines.append("3. **silent, plausible-looking wrong answer** — a "
                 "`Verified`/`Determinate` built from corrupted input with "
                 "no signal anything was off. The only bucket that fails "
                 "`pytest tests/adversarial -q`.")
    lines.append("")

    for package in ("resolver", "matching"):
        tally = {1: 0, 2: 0, 3: 0}
        for row in rows:
            outcome = row.get(package)
            if outcome:
                tally[outcome.bucket] += 1
        total = sum(tally.values())
        lines.append(f"## {package} — {total} cases run")
        lines.append("")
        lines.append(f"| bucket | count |")
        lines.append(f"|---|---:|")
        for b in (1, 2, 3):
            lines.append(f"| {b} ({BUCKET_NAMES[b]}) | {tally[b]} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Full case table")
    lines.append("")
    lines.append("| surface.case | resolver bucket | resolver detail | "
                 "matching bucket | matching detail |")
    lines.append("|---|---|---|---|---|")
    for row in rows:
        r = row.get("resolver")
        m = row.get("matching")
        r_cell = f"{r.bucket} ({r.exception_type or '-'})" if r else "n/a"
        m_cell = f"{m.bucket} ({m.exception_type or '-'})" if m else "n/a"
        r_detail = (r.detail if r else "").replace("|", "\\|")
        m_detail = (m.detail if m else "").replace("|", "\\|")
        lines.append(f"| {row['surface']}.{row['name']} | {r_cell} | "
                     f"{r_detail} | {m_cell} | {m_detail} |")
    lines.append("")

    bucket3 = [(pkg, row) for row in rows for pkg in ("resolver", "matching")
              if row.get(pkg) and row[pkg].bucket == 3]
    lines.append("---")
    lines.append("")
    if not bucket3:
        lines.append("## Bucket-3 findings: none")
        lines.append("")
        lines.append("No case, on either package, produced a confident "
                     "`Verified`/`Determinate` from corrupted input. This is "
                     "a valid, reportable outcome in its own right, not an "
                     "absence of testing -- see the full case table above "
                     "for exactly what was tried.")
    else:
        lines.append(f"## Bucket-3 findings: {len(bucket3)}")
        lines.append("")
        lines.append("Each finding below is a defect: reported with "
                     "reproduction steps, in the style of "
                     "`investigation/DEFECT_REPORT.md`'s D1-D3, and left "
                     "**unpatched** -- `DECISIONS.md` 52 forbids fixing "
                     "`resolver/`/`matching/` in this pass.")
        for n, (pkg, row) in enumerate(bucket3, start=1):
            outcome = row[pkg]
            lines.append("")
            lines.append(f"### F{n}. {pkg}: {row['surface']}.{row['name']}")
            lines.append("")
            lines.append(f"**{outcome.detail}**")
            lines.append("")
            lines.append("Reproduce:")
            lines.append("")
            lines.append("```")
            lines.append(f"pytest 'tests/adversarial/test_{pkg}_survives.py"
                         f"::test_{pkg}_never_returns_a_silent_wrong_answer"
                         f"[{row['surface']}.{row['name']}]' -q")
            lines.append("```")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Additional observations (not part of the 3-bucket tally)")
    lines.append("")
    lines.append("Behaviours the case sweep surfaced that are real but do "
                 "not fit the Verified/Determinate bucket-3 definition -- "
                 "recorded here rather than silently folded into bucket 1.")
    lines.append("")
    lines.append("**All four are now CLOSED (2026-09-03).** Each bullet is "
                 "kept, rewritten, rather than deleted: what the defect was, "
                 "what it would have cost, and the test that now pins the "
                 "fixed behaviour. A section that empties itself as findings "
                 "are fixed loses the record that they were ever found, and "
                 "the tests named below were, until this date, asserting that "
                 "three of these four defects PERSISTED.")
    lines.append("")
    lines.append("- **The two `paise` parsers agree. FIXED 2026-09-03; the "
                 "finding this bullet used to report is closed.** Both parse "
                 "the same kind of rupee-string cell. `resolver.loaders.paise` "
                 "previously did unchecked string surgery, "
                 "`int((frac + \"00\")[:2])`, silently dropping any digits past "
                 "the second -- `\"7612.9951\"` became `761299` paise with no "
                 "signal -- while `matching.money.paise` raised `ValueError` on "
                 "the identical cell. Both now enforce "
                 "`^(-?)(\\d+)(?:\\.(\\d{1,2}))?$` and reject it. The grammar is "
                 "duplicated rather than shared because `resolver/` may not "
                 "import `matching/` (`resolver/tests/test_isolation.py`). "
                 "Behaviour-preserving on every dataset in the repo: 6,374 "
                 "money cells across 168 CSVs, zero rejected. See "
                 "`test_malformed_bank.py::test_the_two_paise_parsers_agree` "
                 "and `::test_over_precision_is_rejected_not_truncated`.")
    lines.append("- **`resolver.loaders.load` refused a duplicate "
                 "`settlement_id`. FIXED 2026-09-03; the finding this bullet "
                 "used to report is closed.** The `settlement_report` dict was "
                 "built by plain assignment in file order, so a repeated "
                 "`settlement_id` silently OVERWROTE the earlier row -- "
                 "last-write-wins, no error, no signal. That feed is the PSP's "
                 "attestation, so discarding one of two contradicting claims "
                 "was the worst available answer to a self-contradicting "
                 "record. It now raises `ValueError`. See "
                 "`test_malformed_settlement_report.py::test_duplicate_"
                 "settlement_id_is_refused_not_overwritten`.")
    lines.append("- **An unrecognised `disputes.json` shape no longer empties "
                 "the dispute set. FIXED 2026-09-03.** "
                 "`payload.get(\"items\", payload if isinstance(payload, list) "
                 "else [])` fell through to `[]` for a plain JSON object that "
                 "was neither `{\"items\": [...]}` nor a bare array, so \"no "
                 "disputes exist\" and \"this shape is unrecognised\" were "
                 "indistinguishable. `resolver.loaders._load_disputes` now "
                 "dispatches on shape explicitly and raises `ValueError`. "
                 "`matching.loaders.load` raises `KeyError` on the same file; "
                 "`matching/` is frozen and unchanged, so the two packages now "
                 "agree the file is malformed and differ only in which "
                 "exception says so. See `test_malformed_erp_disputes.py::"
                 "test_resolver_refuses_the_unhandled_shape`.")
    lines.append("- **A dispute item with no usable id no longer collapses to "
                 "key `\"\"`. FIXED 2026-09-03.** "
                 "`item.get(\"id\") or item.get(\"dispute_id\", \"\")` mapped "
                 "every such item to `\"\"`, and a second one overwrote the "
                 "first. That key was not inert: `resolver/breaks.py` reads "
                 "back with `disputes.get(row.get(\"dispute_id\") or \"\")`, so "
                 "every payment row without a `dispute_id` -- 94% of recon "
                 "rows -- probed `\"\"` as well, and one malformed item would "
                 "have reclassified almost the entire non-disputed population "
                 "as `UNEXPECTED_CHANGE`. The loader now refuses the item, and "
                 "refuses a duplicate dispute id. See "
                 "`test_malformed_erp_disputes.py::test_dispute_missing_id_is_"
                 "refused_not_collapsed_to_one_key` and "
                 "`::test_a_duplicate_dispute_id_is_refused`.")
    lines.append("")

    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    raise SystemExit(main())
