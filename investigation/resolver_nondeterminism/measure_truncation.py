"""Blast-radius measurement for DECISIONS.md sec 58.

Which datasets contain at least one bank line whose closure enumeration does
NOT complete under the current WALL-CLOCK budget? Those, and only those, are
the lines whose composition can move when the budget becomes deterministic.

This measures the CURRENT (pre-fix) code. It changes nothing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
REPO = Path("/Users/deva/razorpay")
sys.path.insert(0, str(REPO))

import resolver.resolve as R                              # noqa: E402
from resolver.enumerate_closures import closing_subsets as _real  # noqa: E402
from resolver.loaders import load                         # noqa: E402

FAMILIES = ("datasets", "datasets_v2", "datasets_gst",
            "datasets_gst_holdout", "datasets_bankside")

CALLS: list[dict] = []


def instrumented(pool, target, **kwargs):
    # WHICH call site matters more than the count. `_verify` uses the closure
    # only for `rival_closure_count` (a self-declared lower bound), so a
    # truncation there cannot move an outcome. `_tier_c` uses `complete` to
    # decide Unresolved vs Reconstructed/Ambiguous, so a truncation there can.
    caller = sys._getframe(1).f_code.co_name
    result = _real(pool, target, **kwargs)
    CALLS.append({
        "caller": caller,
        "pool_rows": len(pool),
        "status": result.status,
        "complete": result.complete,
        "count": result.count,
        "wall_seconds": round(result.wall_seconds, 3),
    })
    return result


R.closing_subsets = instrumented


def dataset_dirs() -> list[Path]:
    out: list[Path] = []
    for family in FAMILIES:
        directory = REPO / "corpus" / family
        if directory.exists():
            out += [d for d in sorted(directory.iterdir())
                    if (d / "recon_combined.json").exists()]
    return out


def main() -> int:
    rows = []
    for directory in dataset_dirs():
        CALLS.clear()
        began = time.perf_counter()
        output = resolve_output = R.resolve(load(directory))
        seconds = time.perf_counter() - began
        calls = list(CALLS)
        incomplete = [c for c in calls if not c["complete"]]
        # `infeasible` is a legitimate complete answer of "no closing subset";
        # only UNKNOWN-ish stops are truncation.
        truncating = [c for c in calls
                      if c["status"] in ("time_budget_exceeded", "cap_reached")]
        row = {
            "dataset": f"{directory.parent.name}/{directory.name}",
            "bank_lines": len(resolve_output.line_outcomes),
            "enumerations": len(calls),
            "truncating": len(truncating),
            "max_pool_rows": max((c["pool_rows"] for c in calls), default=0),
            "statuses": {},
            "seconds": round(seconds, 2),
            "truncating_detail": truncating,
            "outcomes": [type(o).__name__ for o in resolve_output.line_outcomes],
        }
        for c in calls:
            row["statuses"][c["status"]] = row["statuses"].get(c["status"], 0) + 1
        # The two numbers the prediction actually turns on.
        row["tier_c_truncating"] = sum(
            1 for c in truncating if c["caller"] == "_tier_c")
        row["tier_c_time_exceeded"] = sum(
            1 for c in calls if c["caller"] == "_tier_c"
            and c["status"] == "time_budget_exceeded")
        row["verify_time_exceeded"] = sum(
            1 for c in calls if c["caller"] == "_verify"
            and c["status"] == "time_budget_exceeded")
        rows.append(row)
        print(f'{row["dataset"]:<48} lines={row["bank_lines"]:>4} '
              f'enum={row["enumerations"]:>4} TRUNC={row["truncating"]:>3} '
              f'tierC_time={row["tier_c_time_exceeded"]:>3} '
              f'verify_time={row["verify_time_exceeded"]:>3} '
              f'{row["seconds"]:>7.2f}s  {row["statuses"]}', flush=True)

    out = Path(__file__).with_name("truncation_scan.json")
    out.write_text(json.dumps(rows, indent=2))
    total = sum(r["truncating"] for r in rows)
    hit = [r["dataset"] for r in rows if r["truncating"]]
    print(f"\n=== {total} truncating enumerations across "
          f"{len(hit)}/{len(rows)} datasets ===")
    for d in hit:
        print("  ", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
