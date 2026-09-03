"""Watch a `Transport` prefix, ingest new files idempotently, quarantine the
malformed ones, retry the transient failures. This is Track B's answer to the
checklist's **Idempotency & Fault Tolerance** item, which sat at 0% before it:
no `run_id`, no persistence, no atomic writes existed anywhere in the repo.

**Idempotency key is the content digest, not a filename or a timestamp.**
Accepted files land at `dest_dir/<sha256>_<basename>` -- a path that is a
pure function of content, so re-polling the same bytes under the same or a
different remote name is a no-op rather than a duplicate. This is the same
instinct `DATASET_HASHES.txt` applies to frozen data, applied here to
arrivals: a digest is the identity, not a name a caller chose.

**Atomic writes.** Every accepted file is written to a `.tmp-<uuid>` sibling
first, then moved into place with `os.replace` -- POSIX guarantees that as a
single atomic rename, so a crash mid-write can never leave a half-written
file visible at its final path. `poll_once` never observes a partial file: it
either sees the complete one (rename already happened) or none at all
(rename had not happened yet).

**A bad file quarantines and the poll continues.** `validate` is a
caller-supplied callback; if it raises, the file's bytes go to
`quarantine_dir/<sha256>_<basename>` alongside a `.error.txt` naming the
exception, and `poll_once` moves on to the next file rather than stopping the
whole batch over one bad input.

**Retry with exponential backoff and jitter, then a dead letter.** A
`TransientError` from `fetch` is retried up to `max_attempts` times with
delay `base_delay * 2**attempt` plus up to 25% jitter; exhausting attempts
routes the key to `dead_letters` rather than raising out of `poll_once` --
one flaky remote file must not abort an otherwise-healthy batch.
"""

from __future__ import annotations

import hashlib
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from transport.base import Transport


class TransientError(Exception):
    """Raised by a `Transport.fetch` implementation to signal a retryable
    failure (timeout, connection reset) as opposed to a permanent one."""


@dataclass(frozen=True, slots=True)
class PollResult:
    ingested: tuple[str, ...] = ()
    skipped_already_ingested: tuple[str, ...] = ()
    quarantined: tuple[str, ...] = ()
    dead_lettered: tuple[str, ...] = ()


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_write(dest_dir: Path, name: str, payload: bytes) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    final_path = dest_dir / name
    if final_path.exists():
        return final_path
    tmp_path = dest_dir / f".tmp-{uuid.uuid4().hex}"
    tmp_path.write_bytes(payload)
    os.replace(tmp_path, final_path)
    return final_path


def _fetch_with_retry(transport: Transport, key: str, *, max_attempts: int,
                       base_delay: float, sleep: Callable[[float], None],
                       random_fn: Callable[[], float]) -> bytes:
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return transport.fetch(key)
        except TransientError as error:
            last_error = error
            if attempt == max_attempts - 1:
                break
            delay = base_delay * (2 ** attempt) * (1 + 0.25 * random_fn())
            sleep(delay)
    assert last_error is not None
    raise last_error


@dataclass
class Poller:
    transport: Transport
    prefix: str
    dest_dir: Path
    quarantine_dir: Path
    validate: Callable[[bytes], None] = field(default=lambda payload: None)
    max_attempts: int = 5
    base_delay: float = 0.1
    sleep: Callable[[float], None] = field(default=time.sleep)
    random_fn: Callable[[], float] = field(default=random.random)

    def poll_once(self) -> PollResult:
        ingested: list[str] = []
        skipped: list[str] = []
        quarantined: list[str] = []
        dead_lettered: list[str] = []

        for remote_file in self.transport.list(self.prefix):
            try:
                payload = _fetch_with_retry(
                    self.transport, remote_file.key,
                    max_attempts=self.max_attempts, base_delay=self.base_delay,
                    sleep=self.sleep, random_fn=self.random_fn)
            except TransientError:
                dead_lettered.append(remote_file.key)
                continue

            digest = _digest(payload)
            basename = Path(remote_file.key).name
            content_name = f"{digest}_{basename}"

            # Idempotency is keyed on the DIGEST alone, not digest+basename:
            # the same bytes arriving under a different remote filename must
            # still be recognised as already ingested. `content_name` picks a
            # human-readable filename for whichever copy lands first; a later
            # arrival of the same content under a different name is a skip,
            # not a second file.
            already_ingested = self.dest_dir.exists() and any(
                self.dest_dir.glob(f"{digest}_*"))
            if already_ingested:
                skipped.append(remote_file.key)
                continue

            try:
                self.validate(payload)
            except Exception as error:  # noqa: BLE001 -- any validator failure quarantines
                _atomic_write(self.quarantine_dir, content_name, payload)
                error_path = self.quarantine_dir / f"{content_name}.error.txt"
                error_path.write_text(f"{type(error).__name__}: {error}\n")
                quarantined.append(remote_file.key)
                continue

            _atomic_write(self.dest_dir, content_name, payload)
            ingested.append(remote_file.key)

        return PollResult(ingested=tuple(ingested),
                           skipped_already_ingested=tuple(skipped),
                           quarantined=tuple(quarantined),
                           dead_lettered=tuple(dead_lettered))
