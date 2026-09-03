"""`recorded://` transport -- replays a fixture tree captured from a real
backend. Every test in this repo's transport/service suites uses this, never
a live network call, which is what keeps the whole test suite offline and
every existing byte-identity assertion in the repo intact.

`record_fixtures` is the capture side: pull once from a real `Transport`,
write every file under `out_dir`, and write a manifest of redacted
`PullRecord`s next to it -- directly generalising `spike/common.py::log_raw`,
which persists each request/response pair verbatim with the `Authorization`
header redacted: *"This is the evidence trail."* Here the redaction is
structural rather than a header strip: `PullRecord` (`transport/base.py`)
never has a field a credential could land in.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from transport.base import PullRecord, RemoteFile, Transport
from transport.local import LocalTransport

MANIFEST_NAME = "_recorded_manifest.json"


class RecordedTransport:
    def __init__(self, fixture_root: Path) -> None:
        self._local = LocalTransport(Path(fixture_root))

    def list(self, prefix: str) -> list[RemoteFile]:
        return [f for f in self._local.list(prefix) if not f.key.endswith(MANIFEST_NAME)]

    def fetch(self, key: str) -> bytes:
        return self._local.fetch(key)


def record_fixtures(source: Transport, prefix: str, out_dir: Path, *,
                     endpoint: str) -> list[PullRecord]:
    """Pull every file under `prefix` from `source` once, write it under
    `out_dir`, and write a redacted manifest of the pull. `endpoint` is a
    caller-supplied label (never a credential) recorded for provenance."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records: list[PullRecord] = []
    for remote_file in source.list(prefix):
        payload = source.fetch(remote_file.key)
        target = out_dir / remote_file.key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        records.append(PullRecord.ok(
            transport=type(source).__name__, endpoint=endpoint,
            key=remote_file.key, payload=payload))

    manifest_path = out_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps([asdict(r) for r in records], indent=1) + "\n")
    return records
