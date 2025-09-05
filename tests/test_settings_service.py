from __future__ import annotations

import pytest  # type: ignore
from src.db.connection import Database
from src.services.settings import SettingsService


def test_list_available_and_keys(db: Database) -> None:
    svc = SettingsService(db)
    avail = svc.list_available_keys()
    assert "timezone" in avail and "daily_goal_tasks" in avail
    # Empty until set
    assert svc.list_keys() == []
    svc.set("timezone", "UTC")
    assert "timezone" in svc.list_keys()


def test_key_validation_and_blocked(db: Database) -> None:
    svc = SettingsService(db)
    with pytest.raises(ValueError):  # type: ignore
        svc.set("bad key", 1)
    with pytest.raises(PermissionError):  # type: ignore
        svc.get("DISCORD_TOKEN")
    with pytest.raises(PermissionError):  # type: ignore
        svc.delete("token")