"""The three-bucket classifier, shared by every `_survives` test and by
`run_adversarial.py`. Nothing here writes to `resolver/` or `matching/`, and
nothing here calls anything beyond each package's public `load()` +
resolve/cascade entry point -- see `DECISIONS.md` 52.

Bucket 1 -- clean, typed decline: a named exception the package itself
defines (`resolver.loaders.GroundTruthAccess`, `resolver_contract.types.
ContractViolation`, `matching.model.BalanceViolation`), or the resolve/cascade
call completing with no confident positive outcome on the thing that was
corrupted.

Bucket 2 -- an uncaught low-level exception (`KeyError`, `ValueError`, ...).
Allowed; the exact type is what regression-protects it.

Bucket 3 -- the ONLY failing bucket: a `Verified` (resolver) or `Determinate`
(matching) built on the corrupted target with no signal anything was off.

`target_bank_index` (returned by a `Case`'s `mutate`) has three shapes:

* an `int` -- the corruption is scoped to one specific bank line, and a
  confident outcome AT THAT LINE is the bucket-3 candidate.
* `None` -- the corruption is dataset-WIDE (a missing `items` key, a
  zero-row bank file, ...) and should leave nothing left to verify at all;
  any confident outcome anywhere is the bucket-3 candidate.
* the literal string `"n/a"` -- the corrupted surface does not participate
  in Verified/Determinate arithmetic at all (e.g. `disputes.json`'s shape,
  or a bank REFERENCE string when the package's own design routes by
  amount+date rather than by reference -- resolver's Tier B and the frozen
  cascade's Stage 3 solver are both amount-based and reference-blind by
  documented design, not oversight). A confident outcome elsewhere in the
  dataset says nothing about whether THIS corruption was noticed, so no
  bucket-3 check is meaningful here -- see the case-by-case rationale in
  `cases.py` for exactly which cases use this and why.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

BUCKET_CLEAN_DECLINE = 1
BUCKET_UNCAUGHT_EXCEPTION = 2
BUCKET_SILENT_WRONG_ANSWER = 3

NOT_APPLICABLE = "n/a"
Target = "int | None | Literal['n/a']"


@dataclass(frozen=True)
class Outcome:
    bucket: int
    exception_type: str          # "" when no exception fired
    exception_message: str       # "" when no exception fired
    detail: str                  # human-readable, goes straight into the report


def _resolver_typed_exceptions():
    from resolver.loaders import GroundTruthAccess
    from resolver_contract.types import ContractViolation
    return (GroundTruthAccess, ContractViolation)


def _matching_typed_exceptions():
    from matching.model import BalanceViolation
    return (BalanceViolation,)


def classify_resolver(dataset_dir: Path, target_bank_index) -> Outcome:
    from resolver.loaders import load
    from resolver.resolve import resolve
    from resolver_contract.types import Verified

    typed = _resolver_typed_exceptions()

    try:
        dataset = load(dataset_dir)
    except typed as exc:
        return Outcome(BUCKET_CLEAN_DECLINE, type(exc).__name__, str(exc),
                       f"{type(exc).__name__} raised by resolver.loaders.load "
                       "-- a package-defined typed decline")
    except Exception as exc:                                    # noqa: BLE001
        return Outcome(BUCKET_UNCAUGHT_EXCEPTION, type(exc).__name__, str(exc),
                       f"{type(exc).__name__} raised while loading "
                       "(resolver.loaders.load)")

    try:
        output = resolve(dataset)
    except typed as exc:
        return Outcome(BUCKET_CLEAN_DECLINE, type(exc).__name__, str(exc),
                       f"{type(exc).__name__} raised by resolver.resolve.resolve "
                       "-- a package-defined typed decline")
    except Exception as exc:                                    # noqa: BLE001
        return Outcome(BUCKET_UNCAUGHT_EXCEPTION, type(exc).__name__, str(exc),
                       f"{type(exc).__name__} raised while resolving "
                       "(resolver.resolve.resolve)")

    if target_bank_index == NOT_APPLICABLE:
        return Outcome(
            BUCKET_CLEAN_DECLINE, "", "",
            "load()+resolve() completed; the corrupted surface does not "
            "feed Verified's arithmetic (see cases.py for why), so no "
            "bucket-3 check applies here")

    by_line = output.by_line()
    if target_bank_index is not None:
        outcome = by_line.get(target_bank_index)
        if isinstance(outcome, Verified):
            return Outcome(
                BUCKET_SILENT_WRONG_ANSWER, "", "",
                f"bank[{target_bank_index}] resolved Verified "
                f"(rows {outcome.composition.row_ids}) on a dataset the case "
                "deliberately corrupted at this exact line/row")
        return Outcome(
            BUCKET_CLEAN_DECLINE, "", "",
            f"bank[{target_bank_index}] resolved "
            f"{type(outcome).__name__ if outcome else 'no outcome'} "
            "-- not a confident Verified")

    # dataset-wide corruption: any Verified at all on a file that should have
    # produced none is the same finding, just not attributable to one line.
    verified = [o for o in output.line_outcomes if isinstance(o, Verified)]
    if verified:
        return Outcome(
            BUCKET_SILENT_WRONG_ANSWER, "", "",
            f"{len(verified)} Verified outcome(s) produced "
            f"(bank indexes {[o.bank_index for o in verified]}) from a "
            "dataset-wide corruption that should have left nothing to verify")
    return Outcome(BUCKET_CLEAN_DECLINE, "", "",
                   f"resolve() completed with {len(output.line_outcomes)} "
                   "line outcome(s), none Verified")


def classify_matching(dataset_dir: Path, target_bank_index) -> Outcome:
    from matching.loaders import load
    from matching import run as run_cascade
    from matching.model import Determinate

    typed = _matching_typed_exceptions()

    try:
        dataset = load(dataset_dir)
    except typed as exc:
        return Outcome(BUCKET_CLEAN_DECLINE, type(exc).__name__, str(exc),
                       f"{type(exc).__name__} raised by matching.loaders.load "
                       "-- a package-defined typed decline")
    except Exception as exc:                                    # noqa: BLE001
        return Outcome(BUCKET_UNCAUGHT_EXCEPTION, type(exc).__name__, str(exc),
                       "raised while loading (matching.loaders.load)")

    try:
        result = run_cascade(dataset)
    except typed as exc:
        return Outcome(BUCKET_CLEAN_DECLINE, type(exc).__name__, str(exc),
                       f"{type(exc).__name__} raised by matching.cascade.run "
                       "-- a package-defined typed decline")
    except Exception as exc:                                    # noqa: BLE001
        return Outcome(BUCKET_UNCAUGHT_EXCEPTION, type(exc).__name__, str(exc),
                       "raised while running the cascade (matching.cascade.run)")

    if target_bank_index == NOT_APPLICABLE:
        return Outcome(
            BUCKET_CLEAN_DECLINE, "", "",
            "load()+cascade completed; the corrupted surface does not feed "
            "Determinate's arithmetic (see cases.py for why), so no "
            "bucket-3 check applies here")

    by_index = {item.bank_index: item for item in result.stage3.reconstructions}
    if target_bank_index is not None:
        item = by_index.get(target_bank_index)
        resolution = item.resolution if item else None
        if isinstance(resolution, Determinate):
            return Outcome(
                BUCKET_SILENT_WRONG_ANSWER, "", "",
                f"bank[{target_bank_index}] resolved Determinate "
                f"(rows {resolution.decomposition.row_ids}) on a dataset the "
                "case deliberately corrupted at this exact line/row")
        return Outcome(
            BUCKET_CLEAN_DECLINE, "", "",
            f"bank[{target_bank_index}] resolved "
            f"{type(resolution).__name__ if resolution else 'no outcome'} "
            "-- not a confident Determinate")

    determinate = [item for item in result.stage3.reconstructions
                   if isinstance(item.resolution, Determinate)]
    if determinate:
        return Outcome(
            BUCKET_SILENT_WRONG_ANSWER, "", "",
            f"{len(determinate)} Determinate resolution(s) produced "
            f"(bank indexes {[i.bank_index for i in determinate]}) from a "
            "dataset-wide corruption that should have left nothing to close")
    return Outcome(BUCKET_CLEAN_DECLINE, "", "",
                   f"cascade completed with "
                   f"{len(result.stage3.reconstructions)} reconstruction(s), "
                   "none Determinate")
