"""Reproduce DECISIONS.md sec 58 and TRACE THE PROPAGATION PATH.

sec 58 reports: three resolve() calls on the identical in-memory Dataset, and
"first diff at index 56: bank_index=56, both Verified, different composition".

Reading resolver/resolve.py, that is not obviously reachable:

  * `Verified.composition` comes from `claimed`, never from `closures`.
    - tier A: `claimed = state.by_settlement[settlement]` -- fixed.
    - tier B: `claimed = matches[0]`, filtered by `state.consumed`.
  * `_verify`'s `closing_subsets` call feeds ONLY `rival_closure_count` and
    `rival_count_is_lower_bound`.
  * Only `_verify` consumes; `Reconstructed` explicitly does not.

So closure truncation should not be able to move a Verified composition. If it
does, either there is a propagation path I have not found, or there is a
SECOND nondeterminism source -- and in that case swapping
`max_time_in_seconds` for `max_deterministic_time` will not make the resolver
reproducible, which would falsify the whole premise of the planned fix.

This script answers that empirically. It changes nothing.
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

TARGET = REPO / "corpus" / "datasets_gst" / "A20_B100_Cmax_gst"
RUNS = 3

# per-run log of every enumeration, in call order
ENUM_LOG: list[list[dict]] = []
_current: list[dict] = []


def instrumented(pool, target, **kwargs):
    result = _real(pool, target, **kwargs)
    _current.append({"pool_rows": len(pool), "target": target,
                     "status": result.status, "complete": result.complete,
                     "count": result.count,
                     "wall": round(result.wall_seconds, 3)})
    return result


R.closing_subsets = instrumented


def describe(outcome) -> dict:
    """Every field of an outcome, JSON-comparable, nothing dropped."""
    out = {"__type__": type(outcome).__name__}
    if not is_dataclass(outcome):
        return {"__type__": type(outcome).__name__, "repr": repr(outcome)}
    for f in fields(outcome):
        out[f.name] = _plain(getattr(outcome, f.name))
    return out


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
    global _current
    dataset = load(TARGET)          # ONE in-memory object, reused
    runs = []
    for i in range(RUNS):
        _current = []
        output = R.resolve(dataset)
        ENUM_LOG.append(list(_current))
        runs.append([describe(o) for o in output.line_outcomes])
        trunc = [c for c in _current
                 if c["status"] in ("time_budget_exceeded", "cap_reached")]
        print(f"run {i}: {len(output.line_outcomes)} outcomes, "
              f"{len(_current)} enumerations, {len(trunc)} truncating "
              f"{[ (c['pool_rows'], c['status']) for c in trunc ]}", flush=True)

    # --- outcome diffs -----------------------------------------------------
    print("\n=== outcome equality ===")
    for i in range(RUNS):
        for j in range(i + 1, RUNS):
            print(f"run{i} == run{j}: {runs[i] == runs[j]}")

    print("\n=== per-line field-level diffs ===")
    any_diff = False
    for idx in range(len(runs[0])):
        variants = {json.dumps(r[idx], sort_keys=True) for r in runs}
        if len(variants) == 1:
            continue
        any_diff = True
        base = runs[0][idx]
        differing = sorted({
            key for r in runs[1:] for key in base
            if json.dumps(r[idx].get(key), sort_keys=True)
            != json.dumps(base.get(key), sort_keys=True)})
        print(f"\nline {idx}: type={base['__type__']} "
              f"differing fields={differing}")
        for key in differing:
            for i, r in enumerate(runs):
                shown = json.dumps(r[idx].get(key), sort_keys=True)
                print(f"    run{i}.{key} = {shown[:300]}")
    if not any_diff:
        print("  (no differences this session -- did not reproduce)")

    # --- enumeration-log diffs, to locate the CAUSE ------------------------
    print("\n=== enumeration log equality (call order) ===")
    for i in range(RUNS):
        for j in range(i + 1, RUNS):
            same = ENUM_LOG[i] == ENUM_LOG[j]
            print(f"enum log run{i} == run{j}: {same}")
            if not same:
                n = min(len(ENUM_LOG[i]), len(ENUM_LOG[j]))
                for k in range(n):
                    if ENUM_LOG[i][k] != ENUM_LOG[j][k]:
                        print(f"    first differing enumeration #{k}:")
                        print(f"      run{i}: {ENUM_LOG[i][k]}")
                        print(f"      run{j}: {ENUM_LOG[j][k]}")
                        break
                if len(ENUM_LOG[i]) != len(ENUM_LOG[j]):
                    print(f"    LENGTHS DIFFER: {len(ENUM_LOG[i])} vs "
                          f"{len(ENUM_LOG[j])}")

    out = Path(__file__).with_name("reproduce_58.json")
    out.write_text(json.dumps(
        {"runs": runs, "enum_log": ENUM_LOG}, indent=2, sort_keys=True))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
