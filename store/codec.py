"""Generic, lossless dataclass <-> JSON codec for the `resolver_contract.types`
outcome vocabulary.

Every `LineOutcome`/`RowOutcome` variant, and every dataclass nested inside
one (`Warrant`, `Evidence`, `IndependenceDetermination`, `Contradiction`,
`Composition`, `CandidateSet`, `RankingAnnotation`), round-trips through this
codec with no field lost and no type coerced -- an `Evidence.kind` comes back
as the SAME `EvidenceKind` enum member, not its string value; a
`Composition.credit_ids` comes back as a `tuple[str, ...]`, not a `list`.
`store/tests/test_roundtrip.py` is the proof: every outcome type is written
and read back and compared field-for-field, including by `repr()`.

Written generically, over `dataclasses.fields` and `typing.get_type_hints`,
rather than one hand-written (de)serialiser per outcome type -- eight
`LineOutcome`/`RowOutcome` variants times a hand-written pair each is exactly
the kind of duplication a contract change (a ninth variant, a new field) would
then need updated in two places and could silently drift. One codec, driven
by the dataclass definitions themselves, cannot drift from them.
"""

from __future__ import annotations

import enum
import types
import typing
from dataclasses import fields, is_dataclass

import resolver_contract.types as contract

TYPE_KEY = "__type__"


def _resolve_type(cls: type) -> dict[str, type]:
    return typing.get_type_hints(cls, vars(contract))


def to_jsonable(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        result: dict[str, object] = {TYPE_KEY: type(value).__name__}
        for f in fields(value):
            result[f.name] = to_jsonable(getattr(value, f.name))
        return result
    if isinstance(value, (frozenset, set)):
        return sorted(to_jsonable(v) for v in value)
    if isinstance(value, (tuple, list)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    raise TypeError(f"to_jsonable: no rule for {type(value).__name__}")


#: Both spellings of a union origin. `X | None` (PEP 604) evaluates to a
#: `types.UnionType`, while `typing.Optional[X]` evaluates to a `typing.Union`
#: -- and on Python < 3.14 `typing.get_origin` reports these as DIFFERENT
#: objects, so a check against `typing.Union` alone silently misses every
#: `X | None` field in `resolver_contract.types` (they all use PEP 604).
#: Python 3.14 unified the two, which is why this defect was invisible
#: locally and only ever failed on CI's pinned 3.12. See DECISIONS.md.
_UNION_ORIGINS = (typing.Union, types.UnionType)


def _unwrap_optional(tp: object) -> tuple[object, bool]:
    origin = typing.get_origin(tp)
    if origin in _UNION_ORIGINS:
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return tp, False


def from_jsonable(value: object, expected_type: object) -> object:
    expected_type, _optional = _unwrap_optional(expected_type)
    if value is None:
        return None

    origin = typing.get_origin(expected_type)

    if isinstance(expected_type, type) and issubclass(expected_type, enum.Enum):
        return expected_type(value)

    if isinstance(expected_type, type) and is_dataclass(expected_type):
        assert isinstance(value, dict)
        actual_cls = getattr(contract, value[TYPE_KEY]) if TYPE_KEY in value else expected_type
        hints = _resolve_type(actual_cls)
        kwargs = {}
        for f in fields(actual_cls):
            if f.name not in value:
                continue
            kwargs[f.name] = from_jsonable(value[f.name], hints[f.name])
        return actual_cls(**kwargs)

    if origin in (frozenset, set):
        (inner,) = typing.get_args(expected_type)
        return frozenset(from_jsonable(v, inner) for v in value)

    if origin is tuple:
        args = typing.get_args(expected_type)
        if len(args) == 2 and args[1] is Ellipsis:
            inner = args[0]
            return tuple(from_jsonable(v, inner) for v in value)
        return tuple(from_jsonable(v, t) for v, t in zip(value, args))

    if origin is list:
        (inner,) = typing.get_args(expected_type)
        return [from_jsonable(v, inner) for v in value]

    if origin is dict:
        _key_t, val_t = typing.get_args(expected_type)
        return {k: from_jsonable(v, val_t) for k, v in value.items()}

    return value


def outcome_to_jsonable(outcome: object) -> dict:
    """Top-level entry point for a `LineOutcome`/`RowOutcome` value -- always
    tags `__type__` so `outcome_from_jsonable` can dispatch without the
    caller stating the concrete class."""
    result = to_jsonable(outcome)
    assert isinstance(result, dict)
    return result


def outcome_from_jsonable(payload: dict) -> object:
    cls = getattr(contract, payload[TYPE_KEY])
    hints = _resolve_type(cls)
    kwargs = {}
    for f in fields(cls):
        if f.name not in payload:
            continue
        kwargs[f.name] = from_jsonable(payload[f.name], hints[f.name])
    return cls(**kwargs)
