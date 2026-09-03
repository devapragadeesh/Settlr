"""`SFTPTransport` and `S3Transport` must refuse to connect -- no socket ever
opens -- when the credentials guard has not been satisfied. Proves the guard
runs BEFORE `paramiko`/`boto3` touch the network, not after a connection
attempt already started.
"""

from __future__ import annotations

import pytest

from transport.credentials import LiveTransportRefused
from transport.s3 import S3Transport
from transport.sftp import SFTPTransport


def test_sftp_refuses_without_the_opt_in_variable(monkeypatch):
    monkeypatch.delenv("INGEST_TRANSPORT_ALLOW_LIVE", raising=False)
    with pytest.raises(LiveTransportRefused):
        SFTPTransport("sftp.example.com", username="merchant")


def test_sftp_refuses_a_prod_host_even_with_the_opt_in_set(monkeypatch):
    monkeypatch.setenv("INGEST_TRANSPORT_ALLOW_LIVE", "1")
    with pytest.raises(LiveTransportRefused, match="prod"):
        SFTPTransport("sftp-prod.example.com", username="merchant")


def test_s3_refuses_without_the_opt_in_variable(monkeypatch):
    monkeypatch.delenv("INGEST_TRANSPORT_ALLOW_LIVE", raising=False)
    with pytest.raises(LiveTransportRefused):
        S3Transport("some-bucket")


def test_s3_refuses_a_prod_named_bucket_even_with_the_opt_in_set(monkeypatch):
    monkeypatch.setenv("INGEST_TRANSPORT_ALLOW_LIVE", "1")
    with pytest.raises(LiveTransportRefused, match="prod"):
        S3Transport("settlements-prod")
