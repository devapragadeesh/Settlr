"""Generate throughput datasets at increasing volume.

RUNTIME ONLY. Nothing generated here is used for an accuracy claim, and the
held-out evidence never mixes with it -- see `scale/README.md`. These sets
exist to answer one question the Track 04 bar asks first and this project had
no number for: **how fast, and up to what size.**

Built with the FROZEN generator, driven as a library exactly as
`holdout/generate_holdout.py` does. The population constants (`ROLES`,
`EXTRA_REFUNDS`, `MISC_ADJUSTMENTS`, `DECOY_PAIRS`) are rebound on the imported
module to scale volume; `engine/generator.py` on disk is never written.

The batch cadence is deliberately held at the primary set's 12 weekly cut-offs
rather than scaled with volume, so that **eligible pool size is the independent
variable**. That is the quantity `SETTLEMENT_SPEC.md` §1.5 bounds, and the
quantity whose growth this phase is trying to observe.

    python3 scale/generate_scale.py [--sizes 250 1000 10000 25000 50000]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT))

import generator as G                      # noqa: E402  the FROZEN generator

SCALE = ROOT / "scale"

#: the primary set's row count, and therefore the unit the scale factor is in
BASE_ROWS = 240

#: seed for the scale sets. DELIBERATELY NOT the held-out seed: these are a
#: throughput fixture, and reusing the held-out seed would invite the reading
#: that held-out accuracy and scale runtime came from one experiment.
SCALE_SEED = 41


def scaled_roles(factor: float) -> OrderedDict:
    roles = OrderedDict()
    for name, count in G.ROLES.items():
        # every role keeps at least its original count, so no planted
        # construction role can vanish at a small factor
        roles[name] = max(count, int(round(count * factor)))
    return roles


def generate_one(target_rows: int) -> dict:
    factor = target_rows / BASE_ROWS
    base_roles = OrderedDict(G.ROLES)
    base_extra = G.EXTRA_REFUNDS
    base_misc = G.MISC_ADJUSTMENTS
    base_decoys = G.DECOY_PAIRS
    try:
        G.ROLES = scaled_roles(factor)
        G.EXTRA_REFUNDS = max(base_extra, int(round(base_extra * factor)))
        G.MISC_ADJUSTMENTS = max(base_misc, int(round(base_misc * factor)))
        G.DECOY_PAIRS = max(base_decoys, int(round(base_decoys * factor)))

        out = SCALE / f"data_{target_rows}"
        truth = SCALE / f"truth_{target_rows}"
        rows, result, _labels, _bl, _counts = G.generate(SCALE_SEED, out, truth)
    finally:
        G.ROLES = base_roles
        G.EXTRA_REFUNDS = base_extra
        G.MISC_ADJUSTMENTS = base_misc
        G.DECOY_PAIRS = base_decoys

    pools = [b.pool_size for b in result.batches]
    degraded = [b for b in result.batches if b.selection_degraded]
    return {
        "target_rows": target_rows,
        "rows": len(rows),
        "batches": len(result.batches),
        "mean_pool_size": sum(pools) / len(pools) if pools else 0,
        "max_pool_size": max(pools) if pools else 0,
        "min_pool_size": min(pools) if pools else 0,
        "batches_selection_degraded": len(degraded),
        "degraded_pool_sizes": sorted(b.pool_size for b in degraded),
        "undegraded_pool_sizes": sorted(b.pool_size for b in result.batches
                                        if not b.selection_degraded),
        "data_dir": str(out.relative_to(ROOT)),
        "truth_dir": str(truth.relative_to(ROOT)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+",
                        default=[250, 500, 1000, 2500, 5000,
                                 10000, 25000, 50000])
    args = parser.parse_args()

    manifest = []
    for size in args.sizes:
        record = generate_one(size)
        manifest.append(record)
        print(f"{record['rows']:>6} rows  {record['batches']:>3} batches  "
              f"pool mean {record['mean_pool_size']:>7.1f} "
              f"max {record['max_pool_size']:>6}  "
              f"degraded {record['batches_selection_degraded']}/"
              f"{record['batches']}")

    (SCALE / "MANIFEST.json").write_text(json.dumps(
        {"seed": SCALE_SEED, "max_pool": 28,
         "note": "runtime fixture only -- never used for an accuracy claim",
         "sets": manifest}, indent=1) + "\n")


if __name__ == "__main__":
    main()
