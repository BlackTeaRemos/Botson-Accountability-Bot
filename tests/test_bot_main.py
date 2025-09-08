"""Tests for bot_main.py functions."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch
import pytest

from src.core.config import AppConfig
from src.db.connection import Database


def test_json_dumps_compact() -> None:
    """Test JsonDumpsCompact function for deterministic JSON serialization."""
    from src.bot_main import JsonDumpsCompact

    # Test with simple dict
    data1: dict[str, int] = {"b": 2, "a": 1, "c": 3}
    result = JsonDumpsCompact(data1)
    expected = '{"a":1,"b":2,"c":3}'
    assert result == expected

    # Test with nested structure
    data2: dict[str, dict[str, int] | list[int]] = {"nested": {"z": 1, "a": 2}, "list": [3, 1, 2]}
    result = JsonDumpsCompact(data2)
    # Should be sorted by keys
    assert '"a":2' in result
    assert '"z":1' in result
    assert result == json.dumps(data2, separators=(",", ":"), sort_keys=True)


def test_generate_random_user_recent_dry_run() -> None:
    """Test GenerateRandomUserRecent with dry_run=True."""
    from src.commands.debug_functions import make_generate_random_user_recent
    from unittest.mock import Mock

    GenerateRandomUserRecent = make_generate_random_user_recent(Mock())

    channel_id = 12345
    user_id = "test_user"
    messages = 3

    result = GenerateRandomUserRecent(
        channel_discord_id=channel_id,
        user_id=user_id,
        messages=messages,
        within_days=7,
        cluster_days=2,
        jitter_minutes=60,
        dry_run=True
    )

    assert result["user_id"] == user_id
    assert result["written"] is False
    assert len(result["messages"]) == messages

    for msg in result["messages"]:
        assert msg["channel_id"] == channel_id
        assert msg["author_id"] == str(user_id)
        assert msg["author_display"] == str(user_id)
        assert "discord_message_id" in msg
        assert "created_at" in msg
        assert "extracted_date" in msg
        assert msg["content"] == "[x] Habit entry (generated)"


def test_generate_random_user_recent_auto_user_id() -> None:
    """Test GenerateRandomUserRecent with auto-generated user_id."""
    from src.commands.debug_functions import make_generate_random_user_recent
    from unittest.mock import Mock

    GenerateRandomUserRecent = make_generate_random_user_recent(Mock())

    result = GenerateRandomUserRecent(
        channel_discord_id=12345,
        messages=2,
        dry_run=True
    )

    assert result["user_id"].startswith("testuser_")
    assert result["written"] is False
    assert len(result["messages"]) == 2


@patch('src.bot_main.settings')
def test_compute_overridden_config_no_overrides(mock_settings: Mock) -> None:
    """Test _ComputeOverriddenConfig with no DB overrides."""
    from src.computeConfig import _ComputeOverriddenConfig  # type: ignore

    # Mock settings to return None for all values
    mock_settings.get.return_value = None

    base_config = AppConfig(
        discord_token="test_token",
        database_path="/tmp/test.db",
        timezone="UTC",
        use_db_only=False,
        backfill_default_days=30,
        guild_id=None,
        daily_goal_tasks=5,
        scheduled_reports_enabled=False,
        scheduled_report_interval_minutes=60,
        scheduled_report_channel_ids=()
    )

    result = _ComputeOverriddenConfig(base_config)

    # Should return base config unchanged
    assert result.timezone == base_config.timezone
    assert result.use_db_only == base_config.use_db_only
    assert result.backfill_default_days == base_config.backfill_default_days
    assert result.guild_id == base_config.guild_id
    assert result.daily_goal_tasks == base_config.daily_goal_tasks
    assert result.scheduled_reports_enabled == base_config.scheduled_reports_enabled
    assert result.scheduled_report_interval_minutes == base_config.scheduled_report_interval_minutes
    assert result.scheduled_report_channel_ids == base_config.scheduled_report_channel_ids


@patch('src.bot_main.settings')
def test_compute_overridden_config_with_overrides(mock_settings: Mock) -> None:
    """Test _ComputeOverriddenConfig with DB overrides."""
    from src.computeConfig import _ComputeOverriddenConfig  # type: ignore

    # Mock settings to return override values
    def mock_get(key: str) -> str | None:
        overrides = {
            "timezone": "America/New_York",
            "use_db_only": "true",
            "backfill_default_days": "45",
            "guild_id": "123456789",
            "daily_goal_tasks": "10",
            "scheduled_reports_enabled": "1",
            "scheduled_report_interval_minutes": "120",
            "scheduled_report_channel_ids": "111,222,333"
        }
        return overrides.get(key)

    mock_settings.get.side_effect = mock_get

    base_config = AppConfig(
        discord_token="test_token",
        database_path="/tmp/test.db",
        timezone="UTC",
        use_db_only=False,
        backfill_default_days=30,
        guild_id=None,
        daily_goal_tasks=5,
        scheduled_reports_enabled=False,
        scheduled_report_interval_minutes=60,
        scheduled_report_channel_ids=()
    )

    result = _ComputeOverriddenConfig(base_config)

    # Should return config with overrides applied
    assert result.timezone == "America/New_York"
    assert result.use_db_only is True
    assert result.backfill_default_days == 45
    assert result.guild_id == 123456789
    assert result.daily_goal_tasks == 10
    assert result.scheduled_reports_enabled is True
    assert result.scheduled_report_interval_minutes == 120
    assert result.scheduled_report_channel_ids == (111, 222, 333)


@patch('src.bot_main.settings')
def test_compute_overridden_config_invalid_values(mock_settings: Mock) -> None:
    """Test _ComputeOverriddenConfig with invalid DB values."""
    from src.computeConfig import _ComputeOverriddenConfig  # type: ignore

    # Mock settings to return invalid values
    def mock_get(key: str) -> str | None:
        invalid_values: dict[str, str | None] = {
            "backfill_default_days": "invalid",
            "guild_id": "not_a_number",
            "daily_goal_tasks": "",
            "scheduled_report_interval_minutes": None,
            "scheduled_report_channel_ids": "abc,def"
        }
        return invalid_values.get(key)

    mock_settings.get.side_effect = mock_get

    base_config = AppConfig(
        discord_token="test_token",
        database_path="/tmp/test.db",
        timezone="UTC",
        use_db_only=False,
        backfill_default_days=30,
        guild_id=None,
        daily_goal_tasks=5,
        scheduled_reports_enabled=False,
        scheduled_report_interval_minutes=60,
        scheduled_report_channel_ids=(1, 2, 3)
    )

    result = _ComputeOverriddenConfig(base_config)

    # Should fall back to base config defaults for invalid values
    assert result.backfill_default_days == 30  # fallback to base
    assert result.guild_id is None  # fallback to base
    assert result.daily_goal_tasks == 5  # fallback to base
    assert result.scheduled_report_interval_minutes == 60  # fallback to base
    # Accept either fallback to base or empty tuple if parsing fails
    assert result.scheduled_report_channel_ids in [(1, 2, 3), ()]


@patch('src.bot_main.settings')
def test_compute_overridden_config_boolean_variations(mock_settings: Mock) -> None:
    """Test _ComputeOverriddenConfig boolean parsing variations."""
    from src.computeConfig import _ComputeOverriddenConfig  # type: ignore

    def mock_get(key: str) -> str | None:
        if key == "use_db_only":
            return "true"
        elif key == "scheduled_reports_enabled":
            return "0"
        return None

    mock_settings.get.side_effect = mock_get

    base_config = AppConfig(
        discord_token="test_token",
        database_path="/tmp/test.db",
        timezone="UTC",
        use_db_only=False,
        backfill_default_days=30,
        guild_id=None,
        daily_goal_tasks=5,
        scheduled_reports_enabled=True,
        scheduled_report_interval_minutes=60,
        scheduled_report_channel_ids=()
    )

    result = _ComputeOverriddenConfig(base_config)

    assert result.use_db_only is True  # "true" -> True
    assert result.scheduled_reports_enabled is False  # "0" -> False


@patch('src.bot_main.settings')
def test_compute_overridden_config_tuple_parsing(mock_settings: Mock) -> None:
    """Test _ComputeOverriddenConfig tuple parsing variations."""
    from src.computeConfig import _ComputeOverriddenConfig  # type: ignore

    def mock_get(key: str) -> str | None:
        if key == "scheduled_report_channel_ids":
            return "111, 222 , 333"
        return None

    mock_settings.get.side_effect = mock_get

    base_config = AppConfig(
        discord_token="test_token",
        database_path="/tmp/test.db",
        timezone="UTC",
        use_db_only=False,
        backfill_default_days=30,
        guild_id=None,
        daily_goal_tasks=5,
        scheduled_reports_enabled=False,
        scheduled_report_interval_minutes=60,
        scheduled_report_channel_ids=()
    )

    result = _ComputeOverriddenConfig(base_config)

    assert result.scheduled_report_channel_ids == (111, 222, 333)


def test_generate_random_user_recent_with_db(db: Database, seed_channel: int) -> None:
    """Test GenerateRandomUserRecent with actual database writes."""
    from unittest.mock import patch
    from src.services.persistence import PersistenceService
    from src.commands.debug_functions import make_generate_random_user_recent

    # Use a real PersistenceService instance and bind it to the generator
    mock_storage = PersistenceService(db)
    GenerateRandomUserRecent = make_generate_random_user_recent(mock_storage)

    # Use string for channel id to match Channel.discord_channel_id
    result = GenerateRandomUserRecent(
        channel_discord_id=str(seed_channel),
        user_id="db_test_user",
        messages=2,
        dry_run=False,
    )

        assert result["user_id"] == "db_test_user"
        assert result["written"] is True
        assert len(result["messages"]) == 2


def test_generate_random_user_recent_unregistered_channel(db: Database) -> None:
    """Test GenerateRandomUserRecent with unregistered channel."""
    from unittest.mock import patch
    from src.services.persistence import PersistenceService
    from src.commands.debug_functions import make_generate_random_user_recent

    mock_storage = PersistenceService(db)
    GenerateRandomUserRecent = make_generate_random_user_recent(mock_storage)

    # Test with unregistered channel
    with pytest.raises(ValueError, match="Channel .* not registered"):
        GenerateRandomUserRecent(
            channel_discord_id=99999,  # Assuming this channel is not registered
            user_id="test_user",
            messages=1,
            dry_run=False,
        )