"""`sftp://` transport -- real `paramiko` client, gated by
`transport.credentials.require_non_production`.

`paramiko` is imported lazily, inside `__init__`, not at module level: this
keeps `import transport.sftp` cheap for anything that only needs the type
(and keeps a cold clone's dependency footprint honest -- this module is only
ever exercised when a real SFTP pull is authorised).
"""

from __future__ import annotations

from transport.base import RemoteFile
from transport.credentials import require_non_production


class SFTPTransport:
    def __init__(self, host: str, *, port: int = 22, username: str,
                 password: str | None = None,
                 key_filename: str | None = None) -> None:
        require_non_production(host)
        import paramiko  # local import -- see module docstring

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.RejectPolicy())
        self._client.connect(host, port=port, username=username,
                              password=password, key_filename=key_filename)
        self._sftp = self._client.open_sftp()
        self.endpoint = f"sftp://{username}@{host}:{port}"

    def list(self, prefix: str) -> list[RemoteFile]:
        files = []
        for entry in self._sftp.listdir_attr(prefix or "."):
            files.append(RemoteFile(key=f"{prefix.rstrip('/')}/{entry.filename}"
                                     if prefix else entry.filename,
                                     size=entry.st_size or 0))
        return files

    def fetch(self, key: str) -> bytes:
        with self._sftp.open(key, "rb") as handle:
            return handle.read()

    def close(self) -> None:
        self._sftp.close()
        self._client.close()
