"""Nested/paginated JSON and newline-delimited JSON (JSONL) item readers.

`recon_combined.json` is already `{entity, count, items}` -- an API-shaped
envelope, not a bare array -- and every dataset in this repo carries it as one
complete file. Two real-world shapes this module adds beyond that:

1. **Pagination.** A live API rarely returns everything in one response; it
   returns `{"items": [...], "has_more": true}` and expects the caller to
   follow up. `load_paginated_items` merges an ordered sequence of such pages
   and enforces the one invariant that makes "ordered sequence" meaningful:
   every page but the last must claim `has_more=true`, and the last must claim
   `has_more=false`. A page sequence that violates that is a sign a page was
   skipped, duplicated, or mis-ordered -- caught here, not silently merged.
2. **JSONL.** One JSON object per line, read incrementally rather than parsed
   as one giant document -- the shape a streamed export or a Kafka-style log
   dump would actually arrive in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator


def load_items(path: Path) -> list[dict]:
    """`.json` (bare array or `{"items": [...]}`) or `.jsonl` -> `list[dict]`.

    Format is decided by the actual first non-whitespace byte, not by file
    extension -- a `.json` file containing one object per line and a `.jsonl`
    file containing one JSON array both parse correctly, because refusing a
    working file over its extension would be exactly the kind of invented
    rule this repo does not add.
    """
    text = Path(path).read_text()
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped[0] in "[{":
        # Could still be JSONL if it's one object per line without an
        # enclosing array/envelope char at the very start of EVERY line, but
        # the leading byte test is a reliable enough signal: a bare array or
        # an envelope object both start with '[' or '{', and JSONL's first
        # line also starts with '{' -- so a single JSON parse is tried first,
        # and JSONL is the fallback for whatever a single `json.loads` cannot
        # parse as one document.
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return list(_iter_jsonl(text))
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and "items" in payload:
            if not isinstance(payload["items"], list):
                raise ValueError(
                    f"{path}: 'items' must be an array, found "
                    f"{type(payload['items']).__name__}")
            return payload["items"]
        raise ValueError(
            f"{path}: expected a bare array or an object carrying 'items'; "
            f"found object with keys {sorted(payload)!r}")
    return list(_iter_jsonl(text))


def _iter_jsonl(text: str) -> Iterator[dict]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(
                f"line {line_number}: expected a JSON object, found "
                f"{type(item).__name__}")
        yield item


def load_paginated_items(paths: list[Path]) -> list[dict]:
    """Merge an ordered sequence of `{"items": [...], "has_more": bool}`
    pages, enforcing that only the LAST page claims `has_more=false`."""
    if not paths:
        raise ValueError("no pages given")

    items: list[dict] = []
    for position, path in enumerate(paths):
        payload = json.loads(Path(path).read_text())
        if not isinstance(payload, dict) or "items" not in payload or "has_more" not in payload:
            raise ValueError(
                f"{path}: expected an object carrying 'items' and "
                f"'has_more'")
        is_last = position == len(paths) - 1
        has_more = payload["has_more"]
        if is_last and has_more:
            raise ValueError(
                f"{path}: the last page claims has_more=true -- a page is "
                f"missing")
        if not is_last and not has_more:
            raise ValueError(
                f"{path}: page {position} claims has_more=false but is not "
                f"the last page given -- the sequence is wrong or a later "
                f"page is spurious")
        items.extend(payload["items"])
    return items
