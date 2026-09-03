"""The refusal guard -- modelled on `spike/common.py::load_env`'s hard exit
on a non-`rzp_test_` key. No network call is ever made in this file; only the
guard function itself is exercised."""

from __future__ import annotations

import os

import pytest

from transport.credentials import LiveTransportRefused, require_non_production


def test_a_prod_named_endpoint_is_refused_even_with_the_opt_in_set(monkeypatch):
    monkeypatch.setenv("INGEST_TRANSPORT_ALLOW_LIVE", "1")
    with pytest.raises(LiveTransportRefused, match="prod"):
        require_non_production("sftp://bank-prod.example.com")


def test_no_opt_in_variable_refuses_by_default(monkeypatch):
    monkeypatch.delenv("INGEST_TRANSPORT_ALLOW_LIVE", raising=False)
    with pytest.raises(LiveTransportRefused, match="INGEST_TRANSPORT_ALLOW_LIVE"):
        require_non_production("sftp://sandbox.example.com")


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
def test_the_opt_in_variable_authorises_a_non_prod_endpoint(monkeypatch, value):
    monkeypatch.setenv("INGEST_TRANSPORT_ALLOW_LIVE", value)
    require_non_production("sftp://sandbox.example.com")  # must not raise


def test_a_falsy_opt_in_value_still_refuses(monkeypatch):
    monkeypatch.setenv("INGEST_TRANSPORT_ALLOW_LIVE", "0")
    with pytest.raises(LiveTransportRefused):
        require_non_production("sftp://sandbox.example.com")
