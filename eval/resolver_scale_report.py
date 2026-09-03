"""Throughput of the RESOLVER across the `scale/` fixtures — `DECISIONS.md` §53's
deferred measurement, unblocked by §72.

    python3 eval/resolver_scale_report.py [--sizes 250 500 ...]

Writes `scale/RESOLVER_SCALE_REPORT.md` and `scale/resolver_scale_results.json`.

## Why this is a new file and not a flag on `eval/scale_report.py`

`eval/scale_report.py` measures the FROZEN CASCADE and writes
`scale/SCALE_REPORT.md`. It imports `matching.run`, `matching.loaders`,
`matching.model` and `matching.stage3_solver` throughout, and reads
`result.stage3.reconstructions` with per-item `.seconds` / `.pool_ids` /
`.over_time_budget` — none of which exist on a `ResolverOutput`. Repointing it
would also overwrite the frozen cascade's own artifact, which is a published
baseline, and `resolver/tests/test_isolation.py` lists `matching` in
`FORBIDDEN_IMPORTS`, so nothing on the resolver's own import path may reach it
in the first place. Two engines, two reports.

## RUNTIME ONLY. No accuracy claim is made here and none is computed.

Same rule `scale/SCALE_REPORT.md` states for the cascade, and
`tests/test_scale_degradation.py::test_the_scale_fixtures_are_never_used_for_an_accuracy_claim`
fails the build over it.

An answer key for these fixtures does exist, under `scale/truth_*/`. **This
module never opens it, and deliberately contains no path that would.** It could
not use it as-is anyway: that key uses the frozen generator's schema (`utr`,
`credit_ids`/`debit_ids`, no `bank_line_index`, no `planted_classes`), which
`corpus/score_resolver.py` cannot read. Scoring these fixtures would need an
adapter AND its own dated decision; it is not a side effect of timing them.

(The filename is spelled out nowhere above on purpose. `engine/tests/
test_no_leakage.py` scans this package for the literal token by substring, and
an earlier draft of this docstring tripped it by *describing* the key while
never reading it. The right answer was to reword the prose, not to add a
non-reader to `GROUND_TRUTH_ALLOWLIST` -- that list means "this module reads
the key", and putting a module in it that does not would weaken the one
guarantee it exists to make.)

## What this measurement is actually of — read before quoting it

**The resolver returns 12/12 `Verified` at every size, via tier B, and that is
not the scaling success it looks like.**

- Tier A needs `dataset.settlement_report`; **no `scale/data_*` ships a
  `settlement_report.csv`**, so tier A is dead here.
- Recon rows carry `settlement_id`, so `rows_carry_settlement_id` is true and
  every credit line resolves in tier B — a pure-Python scan matching the 12
  settlements against the line amount.
- Tier C, the reconstruction search, is therefore **never reached**, and
  `enumeration_truncated` can never be reported.

So what scales here is `_verify`'s *mandatory rival-count enumeration* — the one
`closing_subsets` call each `Verified` makes over the full eligible pool purely
to populate `rival_closure_count`. That is a real and load-bearing cost, and it
is not the reconstruction search. A reader who takes "12/12 Verified at 48,566
rows" as evidence the resolver scales has been misled by this report unless it
says so first, which is why it says so first.

Measuring tier C at scale needs a fixture whose rows carry no `settlement_id`.
That is a new dataset, not a flag.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import resolver.resolve as resolve_module                             # noqa: E402
from resolver.enumerate_closures import DEFAULT_DETERMINISTIC_BUDGET  # noqa: E402
from resolver.loaders import load                                     # noqa: E402
from resolver.resolve import resolve                                  # noqa: E402
from resolver.run import summarise                                    # noqa: E402

SCALE = ROOT / "scale"
RESULTS = SCALE / "resolver_scale_results.json"
OUT = SCALE / "RESOLVER_SCALE_REPORT.md"


def instrumented(record: list) -> callable:
    """Wrap `closing_subsets` to record what each solve actually faced.

    Measurement only, and deliberately at the CALL SITE rather than inside
    `resolver/`: nothing in the resolver changes to be measured, and the
    package's own hashes stay exactly where they were. `resolve.py` binds the
    name at module scope (`from resolver.enumerate_closures import ...`), so
    rebinding it there is what the resolver will actually call.

    Recording the pool here rather than recomputing it from
    `resolver/eligibility.py::pool_at` is the difference between the pool the
    solver FACED and an upper bound on it. `pool_at` without consumption
    over-reports badly at the top sizes -- rows already taken by earlier lines
    are still in it -- and publishing that next to a timing would misattribute
    the cost.
    """
    original = resolve_module.closing_subsets

    def wrapper(pool, target, **kwargs):
        result = original(pool, target, **kwargs)
        record.append({
            "pool": len(pool),
            "wall_seconds": round(result.wall_seconds, 3),
            "deterministic_seconds": round(result.deterministic_seconds, 4),
            "status": result.status,
            "complete": result.complete,
            "subsets": result.count,
        })
        return result

    resolve_module.closing_subsets = wrapper
    return original


def measure(directory: Path) -> dict:
    dataset = load(directory)
    solves: list[dict] = []
    original = instrumented(solves)
    try:
        start = time.perf_counter()
        output = resolve(dataset)
        seconds = time.perf_counter() - start
    finally:
        resolve_module.closing_subsets = original

    point = summarise(output, seconds)
    point["directory"] = directory.name
    point["rows"] = len(dataset.rows)
    point["bank_lines"] = len(dataset.bank)
    point["wall_clock_seconds"] = round(seconds, 2)
    point["rows_per_second"] = round(len(dataset.rows) / seconds, 1) if seconds else 0

    pools = [s["pool"] for s in solves]
    walls = [s["wall_seconds"] for s in solves]
    point["solves"] = len(solves)
    point["pool_mean"] = round(sum(pools) / len(pools), 1) if pools else 0
    point["pool_max"] = max(pools) if pools else 0
    point["worst_solve_seconds"] = round(max(walls), 2) if walls else 0.0
    point["solves_hitting_budget"] = sum(
        1 for s in solves if s["status"] == "time_budget_exceeded")
    point["solves_hitting_cap"] = sum(
        1 for s in solves if s["status"] == "cap_reached")
    # The ratio this report exists partly to publish: deterministic units are
    # not seconds, and the conversion is a function of pool size.
    worst = max(solves, key=lambda s: s["wall_seconds"]) if solves else None
    if worst and worst["deterministic_seconds"]:
        point["worst_solve_pool"] = worst["pool"]
        point["worst_solve_deterministic"] = worst["deterministic_seconds"]
        point["seconds_per_deterministic_unit"] = round(
            worst["wall_seconds"] / worst["deterministic_seconds"], 2)
    point["per_solve"] = solves
    return point


def sparkline(points, key, width=52) -> list[str]:
    """Plain-text scaling curve, same shape `eval/scale_report.py` uses. No
    dependency: it renders in a terminal and in a diff, which is where this
    will actually be read."""
    values = [p[key] for p in points]
    top = max(values) if values else 1
    lines = []
    for point, value in zip(points, values):
        filled = int(round((value / top) * width)) if top else 0
        lines.append(f"{point['rows']:>6}  {'█' * filled}{'·' * (width - filled)}  "
                     f"{value:>8.2f}s")
    return lines


def write_report(points) -> None:
    out = [
        "# RESOLVER_SCALE_REPORT.md — throughput of the resolver",
        "",
        "Produced by `eval/resolver_scale_report.py`. **Runtime only.** No "
        "accuracy claim is made on this data and none is computed — the same "
        "rule `scale/SCALE_REPORT.md` states for the frozen cascade, enforced "
        "by `tests/test_scale_degradation.py`.",
        "",
        "This is `DECISIONS.md` §53's deferred measurement. §53 gave as its "
        "reason that the fixtures were format-incompatible and that measuring "
        "the resolver at scale would mean generating new corpus-format data. "
        "**That reason was factually wrong** — every `scale/data_*` already "
        "carries a schema-identical `recon_combined.json`, and the only "
        "divergence was two column names in `bank_statement.csv`. §72 fixed it "
        "in eleven lines. No new data was generated for this report.",
        "",
        "## Read this before the table",
        "",
        "**The resolver answers every line in tier B, at every size.** No "
        "`scale/data_*` ships a `settlement_report.csv`, so tier A is dead "
        "here; recon rows carry `settlement_id`, so tier B resolves every "
        "credit; and tier C — the reconstruction search — is **never "
        "reached**. What this report measures is the cost of `_verify`'s "
        "mandatory rival-count enumeration, one `closing_subsets` call per "
        "`Verified` over the full eligible pool. That cost is real. It is not "
        "the reconstruction search, and `12/12 Verified at 48,566 rows` is "
        "**not** evidence that the hard path scales. Measuring the hard path "
        "needs a fixture whose rows carry no `settlement_id` — a new dataset, "
        "not a flag.",
        "",
        "## 1. The measurements",
        "",
        "| rows | bank lines | wall clock | rows/s | solves | pool mean | "
        "pool max | worst solve | budget-bound | Verified |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for p in points:
        out.append(
            f"| {p['rows']:,} | {p['bank_lines']} | {p['wall_clock_seconds']:.2f}s "
            f"| {p['rows_per_second']:,.0f} | {p['solves']} "
            f"| {p['pool_mean']:,.0f} | {p['pool_max']:,} "
            f"| {p['worst_solve_seconds']:.2f}s "
            f"| {p['solves_hitting_budget']}/{p['solves']} | {p['verified']} |")

    out += [
        "",
        "`pool mean`/`pool max` are the pools each CP-SAT solve **actually "
        "faced**, recorded by wrapping `closing_subsets` at the call site — "
        "not recomputed from `pool_at`, which without consumption is an upper "
        "bound that over-reports badly at the top sizes. They are a different "
        "quantity from `scale/SCALE_REPORT.md`'s column, which is "
        "`matching/`'s per-batch pool. **The two must not be compared.**",
        "",
        "`budget-bound` counts solves that stopped on "
        "`max_deterministic_time` rather than finishing or hitting the "
        "solution cap — i.e. where `rival_closure_count` is a lower bound "
        "and `rival_count_is_lower_bound` is set.",
        "",
        "## 2. The scaling curve",
        "",
        "```",
    ]
    out += sparkline(points, "wall_clock_seconds")
    out += [
        "```",
        "",
        "## 3. Why the total is bounded",
        "",
        f"Exactly **one CP-SAT solve per credit line**, each capped by "
        f"`max_deterministic_time = {DEFAULT_DETERMINISTIC_BUDGET}` "
        f"(`resolver/enumerate_closures.py`, §68) and by `DEFAULT_CAP` "
        f"solutions. There is no accumulator across lines and no global "
        f"deadline, so the ceiling is `credit_lines × per_solve` — which is "
        f"why no point here runs away, in contrast to the frozen cascade "
        f"whose per-solve wall budget bound each solve while the solve count "
        f"itself grew.",
        "",
        "**`max_deterministic_time` is not wall-clock, and the conversion is "
        "a function of pool size.** OR-Tools publishes no conversion, by "
        "design — §68 keeps the numeral 10.0 for exactly that reason. This "
        "is the first measurement of the ratio in this repository, taken on "
        "the slowest solve at each size:",
        "",
        "| rows | worst-solve pool | wall | deterministic | seconds per unit |",
        "|---:|---:|---:|---:|---:|",
    ]
    for p in points:
        if "seconds_per_deterministic_unit" not in p:
            continue
        out.append(
            f"| {p['rows']:,} | {p['worst_solve_pool']:,} "
            f"| {p['worst_solve_seconds']:.2f}s "
            f"| {p['worst_solve_deterministic']:.3f} "
            f"| **{p['seconds_per_deterministic_unit']:.2f}** |")
    out += [
        "",
        "Anyone reading `DEFAULT_DETERMINISTIC_BUDGET = 10.0` as \"about ten "
        "seconds\" should read the last column first. The budget is a "
        "*search-effort* bound, not a time bound, and it buys steadily less "
        "wall-clock certainty as the pool grows — which is the property that "
        "makes it deterministic and the property that makes it hard to "
        "capacity-plan against. Both are true and §68 chose the first "
        "deliberately.",
        "",
        "## 4. What this does not say",
        "",
        "- **Nothing about accuracy.** Not measured, not computed, not "
        "claimed. `scale/truth_*` exists but uses the frozen generator's key "
        "schema, which `corpus/score_resolver.py` cannot read; scoring these "
        "fixtures needs an adapter and its own dated decision.",
        "- **Nothing about the reconstruction search**, per the warning above.",
        "- **Nothing about the frozen cascade.** `scale/SCALE_REPORT.md` is "
        "its artifact and is untouched by this script.",
        "",
    ]
    OUT.write_text("\n".join(out) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sizes", type=int, nargs="*", default=None,
                        help="target row counts to run; default all")
    args = parser.parse_args()

    directories = sorted(
        (d for d in SCALE.glob("data_*") if (d / "recon_combined.json").exists()),
        key=lambda d: int(d.name.split("_")[1]))
    if args.sizes:
        wanted = {str(n) for n in args.sizes}
        directories = [d for d in directories if d.name.split("_")[1] in wanted]

    done = {}
    if RESULTS.exists():
        done = {r["directory"]: r
                for r in json.loads(RESULTS.read_text())["points"]}

    def flush(points):
        RESULTS.write_text(json.dumps(
            {"deterministic_budget": DEFAULT_DETERMINISTIC_BUDGET,
             "note": "RUNTIME ONLY -- no accuracy claim. Tier B only; tier C "
                     "is never reached on these fixtures.",
             "points": sorted(points, key=lambda p: p["rows"])}, indent=1) + "\n")

    points = []
    for directory in directories:
        if directory.name in done:
            points.append(done[directory.name])
            print(f"{directory.name:>14}  (cached)")
            continue
        point = measure(directory)
        points.append(point)
        flush(points)                     # resume-safe: written after each point
        print(f"{point['rows']:>6} rows  {point['bank_lines']:>3} lines  "
              f"{point['wall_clock_seconds']:>8.2f}s  "
              f"pool mean {point['pool_mean']:>7.1f} max {point['pool_max']:>6}  "
              f"verified {point['verified']:>3}  "
              f"incomplete {point['incomplete_enumerations']}")

    flush(points)
    write_report(sorted(points, key=lambda p: p["rows"]))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
