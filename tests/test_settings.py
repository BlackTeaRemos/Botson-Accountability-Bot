from __future__ import annotations

import pytest  # type: ignore[import-not-found]

from src.services.settings import SettingsService
from src.db.connection import Database


def test_settings_set_get_delete(db: Database) -> None:
    svc = SettingsService(db)
    # Ensure key absent
    assert svc.get("timezone") is None
    # Set primitive
    svc.set("timezone", "UTC")
    assert svc.get("timezone") == "UTC"
    # Set JSON structure
    svc.set("scheduled_report_channel_ids", [1, 2, 3])
    chan_val = svc.get("scheduled_report_channel_ids")
    assert chan_val is not None and tuple(chan_val) == (1, 2, 3)
    # Delete
    assert svc.delete("timezone") is True
    assert svc.get("timezone") is None


def test_settings_blocked_key(db: Database) -> None:
    svc = SettingsService(db)
    with pytest.raises(PermissionError):  # type: ignore[attr-defined]
        svc.set("DISCORD_TOKEN", "should_not_store")
    with pytest.raises(PermissionError):  # type: ignore[attr-defined]
        _ = svc.get("discord_token")
    with pytest.raises(PermissionError):  # type: ignore[attr-defined]
        svc.delete("token")
