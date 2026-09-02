"""Dump every resolver outcome on every dataset, for the §68 before/after pair.

    python3 investigation/resolver_nondeterminism/before_after.py --label before
    python3 investigation/resolver_nondeterminism/before_after.py --label after
    python3 investigation/resolver_nondeterminism/before_after.py --compare

§39's standard, restated by §49: the pre-fix draw is PUBLISHED alongside the
post-fix one rather than discarded, so a reader can check what the change
actually moved instead of taking the writeup's word for it.

The "before" run is captured by restoring `resolver/enumerate_closures.py`
from git and re-running; it is ONE DRAW of a nondeterministic program, which
is the entire point of the fix and is labelled as such wherever it is used.
`sweep_A_contended.json` and `sweep_B_clean.json` are two further pre-fix
draws of the enumerator statuses.

Every field of every outcome is compared -- not a summary -- because the
prediction's claims are about WHICH fields move, and a summary would hide
exactly the distinction it is trying to make.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import fields, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import resolver.resolve as R                                         # noqa: E402
from resolver.enumerate_closures import closing_subsets as _real     # noqa: E402
from resolver.loaders import load                                    # noqa: E402

FAMILIES = ("datasets", "datasets_v2", "datasets_gst",
            "datasets_gst_holdout", "datasets_bankside")
HERE = Path(__file__).resolve().parent

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
    return {"__type__": type(outcome).__name__,
            **{f.name: _plain(getattr(outcome, f.name)) for f in fields(outcome)}}


def dataset_dirs() -> list[Path]:
    out: list[Path] = []
    for family in FAMILIES:
        directory = ROOT / "corpus" / family
        if directory.exists():
            out += [d for d in sorted(directory.iterdir())
                    if (d / "recon_combined.json").exists()]
    return out


def capture(label: str) -> int:
    global _current
    payload = {}
    for directory in dataset_dirs():
        name = f"{directory.parent.name}/{directory.name}"
        _current = []
        began = time.perf_counter()
        output = R.resolve(load(directory))
        seconds = time.perf_counter() - began
        statuses: dict[str, int] = {}
        for call in _current:
            statuses[call["status"]] = statuses.get(call["status"], 0) + 1
        payload[name] = {
            "outcomes": [describe(o) for o in output.line_outcomes],
            "statuses": statuses,
            "clock_stops_tier_c": sum(
                1 for c in _current if c["caller"] == "_tier_c"
                and c["status"] == "time_budget_exceeded"),
            "clock_stops_verify": sum(
                1 for c in _current if c["caller"] == "_verify"
                and c["status"] == "time_budget_exceeded"),
            "seconds": round(seconds, 2),
        }
        print(f"{name:<48} {statuses}  {seconds:.1f}s", flush=True)
    out = HERE / f"outcomes_{label}.json"
    out.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"\nwrote {out}")
    return 0


def compare() -> int:
    before = json.loads((HERE / "outcomes_before.json").read_text())
    after = json.loads((HERE / "outcomes_after.json").read_text())

    class_changes, field_changes, identical = [], [], []
    composition_changes = []
    stops_before = stops_after = 0

    for name in sorted(before):
        b, a = before[name], after[name]
        stops_before += b["clock_stops_tier_c"] + b["clock_stops_verify"]
        stops_after += a["clock_stops_tier_c"] + a["clock_stops_verify"]
        if b["outcomes"] == a["outcomes"]:
            identical.append(name)
            continue
        classes_b = [o["__type__"] for o in b["outcomes"]]
        classes_a = [o["__type__"] for o in a["outcomes"]]
        if classes_b != classes_a:
            class_changes.append(name)
        moved: dict[str, int] = {}
        for ob, oa in zip(b["outcomes"], a["outcomes"]):
            for key in ob:
                if json.dumps(ob.get(key), sort_keys=True) \
                        != json.dumps(oa.get(key), sort_keys=True):
                    moved[key] = moved.get(key, 0) + 1
                    if key == "composition":
                        composition_changes.append((name, ob.get("bank_index")))
        field_changes.append((name, moved))

    print(f"datasets identical before/after : {len(identical)}/{len(before)}")
    print(f"datasets with ANY field change  : {len(field_changes)}")
    print(f"datasets with an OUTCOME CLASS change : {len(class_changes)} "
          f"{class_changes}")
    print(f"lines with a COMPOSITION change : {len(composition_changes)} "
          f"{composition_changes[:10]}")
    print(f"clock stops before {stops_before} -> after {stops_after}")
    print()
    every_field: dict[str, int] = {}
    for name, moved in field_changes:
        print(f"  {name:<48} {moved}")
        for key, count in moved.items():
            every_field[key] = every_field.get(key, 0) + count
    print(f"\nfields that moved anywhere: {every_field}")

    print("\n--- prediction scorecard ---")
    zero_stop = [n for n in before
                 if not before[n]["clock_stops_tier_c"]
                 and not before[n]["clock_stops_verify"]]
    c1 = all(before[n]["outcomes"] == after[n]["outcomes"] for n in zero_stop)
    print(f"1. zero-clock-stop datasets identical ({len(zero_stop)}): {c1}")
    print(f"2. no outcome CLASS changed anywhere: {not class_changes}")
    print(f"3. no composition changed anywhere: {not composition_changes}")
    print(f"5. (gates) -- checked by re-scoring, not here")
    holdout = "datasets_gst_holdout/A20_B100_Cmax_gst_holdout"
    if holdout in before:
        print(f"   held-out dataset identical: "
              f"{before[holdout]['outcomes'] == after[holdout]['outcomes']}")
    return 0


def identical(labels: list[str]) -> int:
    """§49's verification standard: repeated post-fix runs must be
    byte-identical, INCLUDING one run made deliberately under load.

    Compares full outcome dumps, not summaries. `seconds` is excluded because
    it is wall time and is expected to vary -- that variation is precisely what
    the fix makes irrelevant to the ANSWER, and including it would make a
    passing check impossible for the wrong reason.
    """
    runs = {}
    for label in labels:
        path = HERE / f"outcomes_{label}.json"
        if not path.exists():
            print(f"missing {path}")
            return 1
        runs[label] = json.loads(path.read_text())

    base_label = labels[0]
    base = runs[base_label]
    ok = True
    for label in labels[1:]:
        other = runs[label]
        differing = []
        for name in sorted(base):
            b = {k: v for k, v in base[name].items() if k != "seconds"}
            a = {k: v for k, v in other.get(name, {}).items() if k != "seconds"}
            if b != a:
                fields = sorted(
                    k for k in b if json.dumps(b[k], sort_keys=True)
                    != json.dumps(a.get(k), sort_keys=True))
                differing.append((name, fields))
        print(f"{base_label} == {label}: {not differing}")
        for name, fields in differing:
            ok = False
            print(f"    {name}  differs in {fields}")
    print(f"\nALL {len(labels)} RUNS IDENTICAL: {ok}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--identical", nargs="+")
    arguments = parser.parse_args()
    if arguments.identical:
        return identical(arguments.identical)
    if arguments.compare:
        return compare()
    if not arguments.label:
        parser.error("--label or --compare")
    return capture(arguments.label)


if __name__ == "__main__":
    raise SystemExit(main())
