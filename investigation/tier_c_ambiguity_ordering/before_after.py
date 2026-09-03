"""Dump every resolver outcome on every dataset, for §91's before/after pair.

    python3 investigation/tier_c_ambiguity_ordering/before_after.py --label before
    python3 investigation/tier_c_ambiguity_ordering/before_after.py --label after
    python3 investigation/tier_c_ambiguity_ordering/before_after.py --compare

Adapted from `investigation/resolver_nondeterminism/before_after.py` (§67/§68),
same instrumentation and dump shape. §39's standard: the pre-fix draw is
PUBLISHED alongside the post-fix one rather than discarded, so a reader can
check what the change actually moved instead of taking the writeup's word for
it.

Unlike §68's fix, this one does not touch CP-SAT's search or budget at all --
`closing_subsets` returns byte-identical `Closures` before and after; only
`_tier_c`'s interpretation of an already-returned `Closures` changes. So there
is no "one draw of a nondeterministic program" caveat here: both dumps are
expected to be exactly reproducible on their own, and the only question this
comparison answers is which lines' OUTCOME CLASS moves as a result of the
reordering.

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

    print("\n--- prediction scorecard (sec 91) ---")
    only_unresolved_to_ambiguous = True
    for name, moved in field_changes:
        b, a = before[name]["outcomes"], after[name]["outcomes"]
        for ob, oa in zip(b, a):
            if ob["__type__"] != oa["__type__"]:
                if not (ob["__type__"] == "Unresolved"
                        and oa["__type__"] == "Ambiguous"):
                    only_unresolved_to_ambiguous = False
                    print(f"  UNEXPECTED class change: {name} "
                          f"bank[{ob.get('bank_index')}] "
                          f"{ob['__type__']} -> {oa['__type__']}")
    print(f"1. every outcome-class change is Unresolved -> Ambiguous: "
          f"{only_unresolved_to_ambiguous}")
    print(f"2. no line moved to Reconstructed/Verified: "
          f"{not composition_changes}")
    print(f"3. (gates) -- checked by re-scoring, not here")
    holdout = "datasets_gst_holdout/A20_B100_Cmax_gst_holdout"
    if holdout in before:
        print(f"   held-out dataset identical: "
              f"{before[holdout]['outcomes'] == after[holdout]['outcomes']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label")
    parser.add_argument("--compare", action="store_true")
    arguments = parser.parse_args()
    if arguments.compare:
        return compare()
    if not arguments.label:
        parser.error("--label or --compare")
    return capture(arguments.label)


if __name__ == "__main__":
    raise SystemExit(main())
