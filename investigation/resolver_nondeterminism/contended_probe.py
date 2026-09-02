"""The tier-C probe again, but CONTENDED. sec 49's run-A/run-B logic.

The uncontended probe found `corpus/datasets/A20_Bnone_Cmax` -- 5 tier-C
wall-clock stops, the worst tier-C exposure in the corpus -- bit-identical
across 3 runs. That is evidence, but weak evidence: a WALL-CLOCK budget is
only nondeterministic to the extent the wall clock actually varies, and an
idle machine makes it vary very little. sec 58's original finding surfaced
under a concurrent scoring pass, and sec 49's whole diagnosis rested on an
uncontended run disagreeing with a contended one.

So: run the same 3-run probe while the machine is deliberately loaded with
concurrent CP-SAT work, and see whether the dataset that was stable when idle
is still stable when busy. Nothing here is a fix; this measures the CURRENT
code's exposure so the prediction can state a blast radius honestly.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from dataclasses import fields, is_dataclass
from pathlib import Path

REPO = Path("/Users/deva/razorpay")
sys.path.insert(0, str(REPO))

TARGET = "corpus/datasets/A20_Bnone_Cmax"
RUNS = 3
LOADERS = 6


def _burn(stop_after: float) -> None:
    """Concurrent CP-SAT work, not a spin loop -- the contention has to look
    like what the machine actually does during a scoring pass."""
    sys.path.insert(0, str(REPO))
    from resolver.loaders import load
    from resolver.resolve import resolve
    dataset = load(REPO / "corpus" / "datasets" / "A60_B100_Cmax")
    while time.time() < stop_after:
        resolve(dataset)


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


def main() -> int:
    import resolver.resolve as R
    from resolver.enumerate_closures import closing_subsets as _real
    from resolver.loaders import load

    current: list[dict] = []

    def instrumented(pool, target, **kwargs):
        caller = sys._getframe(1).f_code.co_name
        result = _real(pool, target, **kwargs)
        current.append({"caller": caller, "status": result.status,
                        "count": result.count,
                        "wall": round(result.wall_seconds, 2)})
        return result

    R.closing_subsets = instrumented

    deadline = time.time() + 900
    workers = [mp.Process(target=_burn, args=(deadline,), daemon=True)
               for _ in range(LOADERS)]
    for w in workers:
        w.start()
    print(f"{LOADERS} concurrent resolver processes started", flush=True)
    time.sleep(20)                       # let the load settle

    dataset = load(REPO / TARGET)
    runs, stop_logs = [], []
    for i in range(RUNS):
        current.clear()
        began = time.perf_counter()
        output = R.resolve(dataset)
        runs.append([{"__type__": type(o).__name__,
                      **{f.name: _plain(getattr(o, f.name))
                         for f in fields(o)}} for o in output.line_outcomes])
        stops = [c for c in current if c["status"] == "time_budget_exceeded"]
        stop_logs.append(stops)
        print(f"run {i}: {time.perf_counter() - began:.1f}s  "
              f"clock stops={len(stops)} "
              f"counts={[c['count'] for c in stops]}", flush=True)

    for w in workers:
        w.terminate()

    identical = all(runs[0] == r for r in runs[1:])
    print(f"\nIDENTICAL ACROSS {RUNS} CONTENDED RUNS: {identical}")
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
            print(f"  line {idx:>3} {base['__type__']:<26} fields={changed}")

    Path(__file__).with_name("contended_probe.json").write_text(json.dumps(
        {"target": TARGET, "identical": identical, "diffs": diffs,
         "clock_stop_counts": [[c["count"] for c in s] for s in stop_logs]},
        indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
