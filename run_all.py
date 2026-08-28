#!/usr/bin/env python3
"""One command: run all three systems over every dataset and write the report.

    python3 run_all.py

Runs, in this order:

    1. corpus/triviality_check.py      does a GROUP BY solve the task?
    2. corpus/baseline_old_engine.py   the frozen cascade over every dataset
    3. corpus/score_resolver.py        the new resolver, scored by the oracle
    4. corpus/three_systems.py         the comparison table
    5. corpus/claims_ledger.py         CLAIMS.md, the claims ledger

and writes `corpus/TRIVIALITY_CHECK.md`, `corpus/baseline_results.json`,
`corpus/ORACLE_RESULTS.md`, `corpus/oracle_results.json` and
`corpus/THREE_SYSTEMS.md`.

Expect roughly an hour; measured end to end in a clean checkout at 63m42s
(baseline 2557s, resolver 1265s) -- treat that as one data point, not a
guarantee. The cost is enumeration: the resolver counts rival closing
subsets under NO objective on every line it certifies, because a consequence
confirmed when 400 rival compositions predict the same consequence is weak
corroboration of the one claimed, and contract §3.3 makes that count
mandatory rather than optional. The frozen cascade's own step is bounded by
CP-SAT deterministic time (`DECISIONS.md` §49), not wall-clock time, so its
WALL-CLOCK duration varies with the machine's actual speed even though its
OUTCOME does not -- do not read a faster or slower run as a sign that
something changed. `--quick` lowers the enumeration cap and time budget for
a smoke run; the numbers it produces are NOT the reported ones, because a
lower cap means more truncation and truncation is the abstention loophole.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = [
    ("triviality check",
     [sys.executable, "corpus/triviality_check.py", "--all",
      "--out", "corpus/TRIVIALITY_CHECK.md",
      "--json", "corpus/triviality_results.json"]),
    ("frozen cascade baseline",
     [sys.executable, "corpus/baseline_old_engine.py", "--all",
      "--out", "corpus/baseline_results.json"]),
    ("new resolver, scored by the oracle",
     [sys.executable, "corpus/score_resolver.py", "--all",
      "--out", "corpus/ORACLE_RESULTS.md",
      "--json", "corpus/oracle_results.json"]),
    ("three-system comparison",
     [sys.executable, "corpus/three_systems.py"]),
    ("the claims ledger -- every number, its denominator and its scope",
     [sys.executable, "corpus/claims_ledger.py"]),
    ("the scorecard -- the five-minute read",
     [sys.executable, "corpus/scorecard.py"]),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--quick", action="store_true",
                        help="smoke run at a lower enumeration cap. The "
                             "numbers are not the reported ones.")
    arguments = parser.parse_args()

    for name, command in STEPS:
        if arguments.quick and "score_resolver.py" in command[1]:
            command = command + ["--cap", "20", "--time-budget", "2"]
        print(f"\n=== {name} ===", flush=True)
        began = time.perf_counter()
        completed = subprocess.run(command, cwd=ROOT)
        print(f"--- {name}: {time.perf_counter() - began:.0f}s, exit "
              f"{completed.returncode}", flush=True)
        if completed.returncode != 0:
            print(f"{name} FAILED. Stopping: a partial comparison is worse "
                  "than none, because the missing column looks like a zero.")
            return completed.returncode
    print("\nWrote corpus/THREE_SYSTEMS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
