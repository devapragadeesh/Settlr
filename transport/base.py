"""The `Transport` protocol every backend implements, and the evidence-trail
record every pull writes.

`RemoteFile` and `PullRecord` are frozen dataclasses so a caller cannot
mutate a record after the fact -- the evidence trail is append-only in spirit
even though it currently lives in memory / on disk as flat files (Track C's
`store/` gives it a real home).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RemoteFile:
    key: str
    size: int
    #: Backend-reported modification time, ISO 8601, if the backend has one.
    #: Never used for idempotency -- content SHA-256 is (`transport/poller.py`
    #: in Phase B2) -- only for display and staleness heuristics.
    modified_at: str | None = None


@dataclass(frozen=True, slots=True)
class PullRecord:
    """The redacted evidence trail for one fetch. Never carries a credential
    or the payload itself -- `spike/common.py::log_raw`'s convention, applied
    here to a byte count and a digest rather than a full response body,
    because a settlement file can be megabytes and the evidence that matters
    is what it hashed to, not a second copy of it."""

    transport: str
    endpoint: str
    key: str
    byte_count: int
    sha256: str
    fetched_at: str
    outcome: str  # "ok" or an error class name

    @staticmethod
    def ok(*, transport: str, endpoint: str, key: str, payload: bytes) -> "PullRecord":
        return PullRecord(
            transport=transport, endpoint=endpoint, key=key,
            byte_count=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            outcome="ok")


class Transport(Protocol):
    def list(self, prefix: str) -> list[RemoteFile]: ...

    def fetch(self, key: str) -> bytes: ...
