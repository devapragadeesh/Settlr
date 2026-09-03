"""`file://` transport -- reads a local directory tree. No network, no
credentials guard needed (there is nothing to authenticate to)."""

from __future__ import annotations

from pathlib import Path

from transport.base import RemoteFile


class LocalTransport:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def list(self, prefix: str) -> list[RemoteFile]:
        base = self.root / prefix
        if not base.exists():
            return []
        files = []
        for path in sorted(base.rglob("*")):
            if path.is_file():
                key = str(path.relative_to(self.root))
                stat = path.stat()
                files.append(RemoteFile(key=key, size=stat.st_size))
        return files

    def fetch(self, key: str) -> bytes:
        path = self.root / key
        if not path.is_file():
            raise FileNotFoundError(f"{key!r} not found under {self.root}")
        return path.read_bytes()
