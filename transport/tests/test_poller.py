"""Poller: idempotency, quarantine, atomic writes, retry/dead-letter. All
offline -- `LocalTransport` and a hand-written flaky fake, no real network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transport.base import RemoteFile
from transport.local import LocalTransport
from transport.poller import Poller, TransientError, _digest


def _seed(root: Path, name: str, content: bytes) -> None:
    (root / "incoming").mkdir(parents=True, exist_ok=True)
    (root / "incoming" / name).write_bytes(content)


def test_a_fresh_poll_ingests_every_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    content_a = b"a,b\n1,2\n"
    content_b = b"c,d\n3,4\n"
    _seed(source, "a.csv", content_a)
    _seed(source, "b.csv", content_b)

    poller = Poller(transport=LocalTransport(source), prefix="incoming",
                     dest_dir=tmp_path / "dest", quarantine_dir=tmp_path / "quarantine")
    result = poller.poll_once()

    assert set(result.ingested) == {"incoming/a.csv", "incoming/b.csv"}
    assert result.skipped_already_ingested == ()
    landed = {p.name for p in (tmp_path / "dest").iterdir()}
    assert landed == {f"{_digest(content_a)}_a.csv", f"{_digest(content_b)}_b.csv"}


def test_kill_and_resume_ingests_exactly_once_and_loses_nothing(tmp_path: Path) -> None:
    """Simulates a crash after the first poll committed its files: a second
    Poller instance (fresh in-memory state, same dest_dir) re-polls the SAME
    source. Idempotency must come from content on disk, not in-memory
    state, so this is the real proof -- not "the same object remembers,"
    but "a brand new poller reaches the same, non-duplicated answer."""
    source = tmp_path / "source"
    _seed(source, "a.csv", b"a,b\n1,2\n")
    _seed(source, "b.csv", b"c,d\n3,4\n")

    dest = tmp_path / "dest"
    quarantine = tmp_path / "quarantine"

    first = Poller(transport=LocalTransport(source), prefix="incoming",
                    dest_dir=dest, quarantine_dir=quarantine)
    first_result = first.poll_once()
    assert len(first_result.ingested) == 2

    # A third file arrives between polls -- the resumed poll must pick it up
    # while re-confirming the first two are already there, not re-ingesting.
    _seed(source, "c.csv", b"e,f\n5,6\n")

    second = Poller(transport=LocalTransport(source), prefix="incoming",
                     dest_dir=dest, quarantine_dir=quarantine)
    second_result = second.poll_once()

    assert set(second_result.skipped_already_ingested) == {"incoming/a.csv", "incoming/b.csv"}
    assert second_result.ingested == ("incoming/c.csv",)

    landed = list(dest.iterdir())
    assert len(landed) == 3, "no duplicate and no lost file after resume"
    assert not any(p.name.startswith(".tmp-") for p in landed), \
        "no atomic-write temp file left behind"


def test_a_file_that_fails_validation_is_quarantined_and_the_poll_continues(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _seed(source, "good.csv", b"ok")
    _seed(source, "bad.csv", b"BAD")

    def validate(payload: bytes) -> None:
        if payload == b"BAD":
            raise ValueError("payload is literally BAD")

    poller = Poller(transport=LocalTransport(source), prefix="incoming",
                     dest_dir=tmp_path / "dest", quarantine_dir=tmp_path / "quarantine",
                     validate=validate)
    result = poller.poll_once()

    assert result.ingested == ("incoming/good.csv",)
    assert result.quarantined == ("incoming/bad.csv",)
    quarantined_files = list((tmp_path / "quarantine").iterdir())
    assert any(p.name.endswith(".error.txt") and "payload is literally BAD" in p.read_text()
               for p in quarantined_files)


def test_a_transient_failure_retries_then_succeeds(tmp_path: Path) -> None:
    class FlakyTransport:
        def __init__(self) -> None:
            self.attempts = 0

        def list(self, prefix: str) -> list[RemoteFile]:
            return [RemoteFile(key="incoming/a.csv", size=5)]

        def fetch(self, key: str) -> bytes:
            self.attempts += 1
            if self.attempts < 3:
                raise TransientError("connection reset")
            return b"final"

    flaky = FlakyTransport()
    sleeps: list[float] = []
    poller = Poller(transport=flaky, prefix="incoming", dest_dir=tmp_path / "dest",
                     quarantine_dir=tmp_path / "quarantine",
                     base_delay=0.01, sleep=sleeps.append, random_fn=lambda: 0.0)
    result = poller.poll_once()

    assert flaky.attempts == 3
    assert result.ingested == ("incoming/a.csv",)
    assert len(sleeps) == 2, "two retries before the third, successful attempt"


def test_a_permanently_failing_fetch_is_dead_lettered_not_raised(tmp_path: Path) -> None:
    class AlwaysFlaky:
        def list(self, prefix: str) -> list[RemoteFile]:
            return [RemoteFile(key="incoming/a.csv", size=5),
                    RemoteFile(key="incoming/b.csv", size=5)]

        def fetch(self, key: str) -> bytes:
            if key == "incoming/a.csv":
                raise TransientError("always fails")
            return b"ok"

    poller = Poller(transport=AlwaysFlaky(), prefix="incoming",
                     dest_dir=tmp_path / "dest", quarantine_dir=tmp_path / "quarantine",
                     max_attempts=3, base_delay=0.0, sleep=lambda s: None,
                     random_fn=lambda: 0.0)
    result = poller.poll_once()

    assert result.dead_lettered == ("incoming/a.csv",)
    assert result.ingested == ("incoming/b.csv",)


def test_the_same_content_under_a_different_remote_name_is_recognised_as_already_ingested(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _seed(source, "a.csv", b"same,bytes\n")

    dest = tmp_path / "dest"
    quarantine = tmp_path / "quarantine"
    Poller(transport=LocalTransport(source), prefix="incoming",
           dest_dir=dest, quarantine_dir=quarantine).poll_once()

    (source / "incoming" / "a_renamed_copy.csv").write_bytes(b"same,bytes\n")
    result = Poller(transport=LocalTransport(source), prefix="incoming",
                     dest_dir=dest, quarantine_dir=quarantine).poll_once()

    assert "incoming/a_renamed_copy.csv" in result.skipped_already_ingested
    assert len(list(dest.iterdir())) == 1, "content-addressed, so a rename is not a new file"
