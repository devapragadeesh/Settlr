"""`s3://` transport -- real `boto3` client, gated by
`transport.credentials.require_non_production`.

`boto3` is imported lazily, inside `__init__`, for the same reason
`transport/sftp.py` imports `paramiko` lazily: this module's dependency is
paid only when a real S3 pull is authorised. Credentials are resolved by
boto3's own standard chain (environment, shared config, instance role) --
never read or written by this module directly.
"""

from __future__ import annotations

from transport.base import RemoteFile
from transport.credentials import require_non_production


class S3Transport:
    def __init__(self, bucket: str, *, region: str | None = None) -> None:
        require_non_production(bucket)
        import boto3  # local import -- see module docstring

        self._bucket = bucket
        self._client = boto3.client("s3", region_name=region)
        self.endpoint = f"s3://{bucket}"

    def list(self, prefix: str) -> list[RemoteFile]:
        files = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                files.append(RemoteFile(
                    key=obj["Key"], size=obj["Size"],
                    modified_at=obj["LastModified"].isoformat()
                    if obj.get("LastModified") else None))
        return files

    def fetch(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()
