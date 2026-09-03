"""`resolve_role` must agree with `resolver.loaders._bank_column` exactly,
on the two real header shapes on disk, and must keep Sec.72's two rules:
no guessing when a role is absent, no preference when two spellings collide.
"""

from __future__ import annotations

import pytest

from ingest.schema import BANK_ROLES, RoleConflict, RoleMissing, resolve_role
from resolver.loaders import _bank_column


CORPUS_HEADER = ("bank_reference", "value_date", "narration", "amount")
FROZEN_HEADER = ("utr", "date", "narration", "amount")

_REFERENCE = BANK_ROLES[0]
_VALUE_DATE = BANK_ROLES[1]


@pytest.mark.parametrize("header", [CORPUS_HEADER, FROZEN_HEADER])
def test_resolve_role_agrees_with_the_frozen_bank_column_helper(header):
    for role, old_role_name in ((_REFERENCE, "reference"), (_VALUE_DATE, "value_date")):
        got = resolve_role(role, header)
        want = _bank_column(old_role_name, list(header), path=None)
        assert got == want


def test_two_spellings_present_at_once_is_a_conflict_not_a_preference():
    header = ("bank_reference", "utr", "narration", "amount")
    with pytest.raises(RoleConflict):
        resolve_role(_REFERENCE, header)


def test_a_required_role_missing_entirely_raises():
    header = ("narration", "amount")
    with pytest.raises(RoleMissing):
        resolve_role(_REFERENCE, header)


def test_an_optional_role_missing_returns_none():
    from ingest.schema import Role
    from resolver_contract.types import SourceSystem
    optional = Role("foo", SourceSystem.BANK, ("foo",), required=False)
    assert resolve_role(optional, ("narration", "amount")) is None
