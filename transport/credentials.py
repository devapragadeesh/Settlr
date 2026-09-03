"""The refusal guard every real (non-recorded) transport backend calls before
it opens a connection.

Directly modelled on `spike/common.py::load_env`, which hard-exits rather than
proceeding when a key id is not prefixed `rzp_test_`: *"FATAL: refusing to
run -- key id ... is not rzp_test_*. LIVE KEYS ARE FORBIDDEN IN THIS SPIKE."*
There is no equivalent universal prefix convention for SFTP hosts or S3
buckets, so the guard here is an explicit opt-in instead: a real backend
refuses to connect unless `INGEST_TRANSPORT_ALLOW_LIVE=1` is set in the
environment, and refuses outright -- opt-in or not -- if the endpoint string
itself contains the literal `"prod"`, case-insensitively, as a second,
independent net.

Credentials themselves are read from the environment only (`SFTP_*`,
`AWS_*`/`boto3`'s own resolution chain) -- never written to disk, never
logged, never placed in a `PullRecord` (`transport/base.py`), which carries
only a byte count and a digest.
"""

from __future__ import annotations

import os


class LiveTransportRefused(Exception):
    """A real transport backend was asked to connect without explicit
    authorisation, or against an endpoint naming itself production."""


def require_non_production(endpoint: str, *, env_var: str = "INGEST_TRANSPORT_ALLOW_LIVE") -> None:
    if "prod" in endpoint.lower():
        raise LiveTransportRefused(
            f"refusing to connect to {endpoint!r}: contains 'prod' -- this "
            f"guard cannot be overridden by the opt-in environment variable, "
            f"only by using a differently-named endpoint")
    if os.environ.get(env_var, "").strip().lower() not in ("1", "true", "yes"):
        raise LiveTransportRefused(
            f"refusing to connect to {endpoint!r}: set {env_var}=1 to "
            f"authorise a real network transport. Tests must use "
            f"transport.recorded.RecordedTransport instead.")
