"""Shared fixtures. Loads the FROZEN dataset from disk, not a fresh run --
tests must fail if the committed data and the generator ever diverge."""

import csv
import json
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

DATA = ENGINE / "data"
TRUTH = ENGINE / "ground_truth"
CAPTURED = ENGINE.parent / "spike" / "captured_dataset.json"


def _csv(path):
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="session")
def recon():
    return json.loads((DATA / "recon_combined.json").read_text())


@pytest.fixture(scope="session")
def rows(recon):
    return recon["items"]


@pytest.fixture(scope="session")
def truth():
    return json.loads((TRUTH / "ground_truth.json").read_text())


@pytest.fixture(scope="session")
def disputes():
    return json.loads((DATA / "disputes.json").read_text())["items"]


@pytest.fixture(scope="session")
def bank():
    return _csv(DATA / "bank_statement.csv")


@pytest.fixture(scope="session")
def erp():
    return _csv(DATA / "erp_orders.csv")


@pytest.fixture(scope="session")
def gstr2b():
    return _csv(DATA / "gstr2b.csv")


@pytest.fixture(scope="session")
def captured():
    return json.loads(CAPTURED.read_text())
