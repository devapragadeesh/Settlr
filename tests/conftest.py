"""Fixtures for the cascade tests.

The cascade is expensive enough that it is built once per session and shared.
`eval/` may read the ground-truth key; `matching/` may not, and
`test_no_leakage.py` enforces that structurally.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def cascade():
    from matching import run
    return run()


@pytest.fixture(scope="session")
def truth():
    from eval.metrics import load_truth
    return load_truth()


@pytest.fixture(scope="session")
def scored(cascade, truth):
    from eval.metrics import score
    return score(cascade, truth)


@pytest.fixture(scope="session")
def dataset(cascade):
    return cascade.dataset
