"""Tests for security utilities."""
from __future__ import annotations

import pytest

from src.security import validate_discord_token
from src.security.permissions import has_admin, has_manage_guild


def test_validate_discord_token_valid() -> None:
    # Discord tokens have 3 parts separated by '.'; content is not validated here.
    validate_discord_token("aaaa.bbbb.cccc")


@pytest.mark.parametrize("token", ["", "changeme", None, "one.two"])  # type: ignore[list-item]
def test_validate_discord_token_invalid(token) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SystemExit):
        validate_discord_token(token)  # type: ignore[arg-type]


class _Perms:
    def __init__(self, admin: bool = False, manage: bool = False):
        self.administrator = admin  # primitive flag
        self.manage_guild = manage  # primitive flag


class _User:
    def __init__(self, perms: _Perms):
        self.guild_permissions = perms


class _Interaction:
    def __init__(self, admin: bool = False, manage: bool = False):
        self.user = _User(_Perms(admin, manage))
        self.guild_id = 123


def test_has_admin_and_manage() -> None:
    i1 = _Interaction(admin=True, manage=False)
    i2 = _Interaction(admin=False, manage=True)
    i3 = _Interaction(admin=False, manage=False)

    assert has_admin(i1) is True
    assert has_manage_guild(i1) is False

    assert has_admin(i2) is False
    assert has_manage_guild(i2) is True

    assert has_admin(i3) is False
    assert has_manage_guild(i3) is False
