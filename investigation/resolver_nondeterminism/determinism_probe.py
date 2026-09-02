"""Test the MODEL behind the sec 58 prediction, before the fix is written.

The model says the pre-fix resolver's run-to-run instability is confined to
enumerations the WALL CLOCK cut off (`time_budget_exceeded`), and that
`cap_reached` is NOT a source of instability: with `num_workers = 1` and a
fixed `random_seed`, CP-SAT's solution ORDER is reproducible, so the first
`cap` solutions are the same set every time regardless of the clock.

Two falsifiable consequences, tested here on the CURRENT (unfixed) code:

  A. A dataset with ZERO `time_budget_exceeded` is bit-identical across runs
     EVEN IF it is heavily `cap_reached`. If one of these differs, the model
     is wrong and `cap_reached` is a second nondeterminism source that
     `max_deterministic_time` would NOT fix.

  B. A dataset with several TIER-C `time_budget_exceeded` differs across
     runs, and the differing lines are Unresolved/Reconstructed/Ambiguous --
     not merely `rival_closure_count` on a Verified line, which is all that
     moved on the GST set.

Each dataset is resolved 3x on ONE in-memory object, so filesystem and
process-startup variance are excluded.
"""
from __future__ import annotations

import json
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path

REPO = Path("/Users/deva/razorpay")
sys.path.insert(0, str(REPO))

import resolver.resolve as R                              # noqa: E402
from resolver.enumerate_closures import closing_subsets as _real  # noqa: E402
from resolver.loaders import load                         # noqa: E402

RUNS = 3
TARGETS = [
    # (path, prediction)
    ("corpus/datasets/A40_B50_Cmax", "IDENTICAL (cap-heavy, no clock stop)"),
    ("corpus/datasets_gst_holdout/A20_B100_Cmax_gst_holdout",
     "IDENTICAL (all optimal)"),
    ("corpus/datasets/A20_Bnone_Cmax", "DIFFERS (5 tier-C clock stops)"),
]

_current: list[dict] = []


def instrumented(pool, target, **kwargs):
    caller = sys._getframe(1).f_code.co_name
    result = _real(pool, target, **kwargs)
    _current.append({"caller": caller, "status": result.status,
                     "count": result.count, "complete": result.complete})
    return result


R.closing_subsets = instrumented


def _plain(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(v) for v in value)
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def describe(outcome) -> dict:
    out = {"__type__": type(outcome).__name__}
    for f in fields(outcome):
        out[f.name] = _plain(getattr(outcome, f.name))
    return out


def main() -> int:
    global _current
    report = {}
    for rel, prediction in TARGETS:
        directory = REPO / rel
        dataset = load(directory)
        runs, logs = [], []
        for _ in range(RUNS):
            _current = []
            output = R.resolve(dataset)
            logs.append(list(_current))
            runs.append([describe(o) for o in output.line_outcomes])

        stops = [c for c in logs[0] if c["status"] == "time_budget_exceeded"]
        caps = [c for c in logs[0] if c["status"] == "cap_reached"]
        identical = all(runs[0] == r for r in runs[1:])

        diffs = []
        for idx in range(len(runs[0])):
            if len({json.dumps(r[idx], sort_keys=True) for r in runs}) > 1:
                base = runs[0][idx]
                changed = sorted({
                    k for r in runs[1:] for k in base
                    if json.dumps(r[idx].get(k), sort_keys=True)
                    != json.dumps(base.get(k), sort_keys=True)})
                diffs.append({"line": idx, "type": base["__type__"],
                              "fields": changed})

        print(f"\n=== {rel}")
        print(f"    predicted: {prediction}")
        print(f"    clock stops: {len(stops)} "
              f"({sum(1 for c in stops if c['caller'] == '_tier_c')} tier-C, "
              f"{sum(1 for c in stops if c['caller'] == '_verify')} verify)"
              f"   cap_reached: {len(caps)}")
        print(f"    IDENTICAL ACROSS {RUNS} RUNS: {identical}")
        for d in diffs:
            print(f"      line {d['line']:>3} {d['type']:<24} "
                  f"fields={d['fields']}")
        report[rel] = {"prediction": prediction, "identical": identical,
                       "clock_stops": len(stops),
                       "clock_stops_tier_c":
                           sum(1 for c in stops if c["caller"] == "_tier_c"),
                       "cap_reached": len(caps), "diffs": diffs}

    out = Path(__file__).with_name("determinism_probe.json")
    out.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
