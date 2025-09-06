"""Tests for core configuration modules."""

from __future__ import annotations

import os
from unittest.mock import patch
import pytest

from src.core.dynaconf_settings import _ParseChannelIds, GetSettings, AppConfig  # type: ignore


def test_parse_channel_ids_none() -> None:
    """Test _ParseChannelIds with None input."""
    result = _ParseChannelIds(None)
    assert result == ()


def test_parse_channel_ids_list() -> None:
    """Test _ParseChannelIds with list input."""
    result = _ParseChannelIds([123, 456, "789"])
    assert result == (123, 456, 789)


def test_parse_channel_ids_tuple() -> None:
    """Test _ParseChannelIds with tuple input."""
    result = _ParseChannelIds((123, 456))
    assert result == (123, 456)


def test_parse_channel_ids_csv_string() -> None:
    """Test _ParseChannelIds with CSV string input."""
    result = _ParseChannelIds("123, 456 , 789")
    assert result == (123, 456, 789)


def test_parse_channel_ids_empty_string() -> None:
    """Test _ParseChannelIds with empty string."""
    result = _ParseChannelIds("")
    assert result == ()


def test_parse_channel_ids_invalid_values() -> None:
    """Test _ParseChannelIds with invalid values in CSV."""
    with pytest.raises(ValueError):
        _ParseChannelIds("123, invalid, 456")


def test_parse_channel_ids_whitespace_only() -> None:
    """Test _ParseChannelIds with whitespace-only values."""
    result = _ParseChannelIds("123, , 456,   ")
    assert result == (123, 456)


@patch('src.core.dynaconf_settings.settings')
def test_get_settings_basic(mock_settings) -> None:
    """Test GetSettings with basic configuration."""
    # Mock settings to return basic values
    mock_settings.get.side_effect = lambda key, default=None: {
        "DISCORD_TOKEN": "test_token_123",
        "DB_PATH": "/tmp/test.db",
        "BOT_TZ": "UTC",
        "USE_DB_ONLY": True,
        "BACKFILL_DEFAULT_DAYS": 45,
        "GUILD_ID": 123456789,
        "DAILY_GOAL_TASKS": 10,
        "SCHEDULED_REPORTS_ENABLED": False,
        "SCHEDULED_REPORT_INTERVAL_MINUTES": 120,
        "SCHEDULED_REPORT_CHANNEL_IDS": [111, 222]
    }.get(key, default)

    result = GetSettings()

    assert isinstance(result, AppConfig)
    assert result.discord_token == "test_token_123"
    assert result.database_path == "/tmp/test.db"
    assert result.timezone == "UTC"
    assert result.use_db_only is True
    assert result.backfill_default_days == 45
    assert result.guild_id == 123456789
    assert result.daily_goal_tasks == 10
    assert result.scheduled_reports_enabled is False
    assert result.scheduled_report_interval_minutes == 120
    assert result.scheduled_report_channel_ids == (111, 222)


@patch('src.core.dynaconf_settings.settings')
@patch.dict(os.environ, {'DISCORD_TOKEN': 'env_token_456'})
def test_get_settings_token_fallback_to_env(mock_settings) -> None:
    """Test GetSettings token fallback to environment variable."""
    # Mock settings to return None for token
    mock_settings.get.side_effect = lambda key, default=None: {
        "DISCORD_TOKEN": None,
        "DB_PATH": "bot.db",
        "BOT_TZ": "America/New_York",
    }.get(key, default)

    result = GetSettings()

    assert result.discord_token == "env_token_456"


@patch('src.core.dynaconf_settings.settings')
@patch.dict(os.environ, {}, clear=True)
def test_get_settings_token_empty_fallback(mock_settings) -> None:
    """Test GetSettings token fallback when env var is missing."""
    # Mock settings to return None for token
    mock_settings.get.side_effect = lambda key, default=None: {
        "DISCORD_TOKEN": None,
        "DB_PATH": "bot.db",
    }.get(key, default)

    result = GetSettings()

    assert result.discord_token == ""


@patch('src.core.dynaconf_settings.settings')
def test_get_settings_guild_id_none(mock_settings) -> None:
    """Test GetSettings with None guild_id."""
    mock_settings.get.side_effect = lambda key, default=None: {
        "DISCORD_TOKEN": "test_token",
        "GUILD_ID": None,
    }.get(key, default)

    result = GetSettings()

    assert result.guild_id is None


@patch('src.core.dynaconf_settings.settings')
def test_get_settings_guild_id_zero(mock_settings) -> None:
    """Test GetSettings with zero guild_id (treated as None)."""
    mock_settings.get.side_effect = lambda key, default=None: {
        "DISCORD_TOKEN": "test_token",
        "GUILD_ID": 0,
    }.get(key, default)

    result = GetSettings()

    assert result.guild_id is None


@patch('src.core.dynaconf_settings.settings')
def test_get_settings_channel_ids_empty(mock_settings) -> None:
    """Test GetSettings with empty channel IDs."""
    mock_settings.get.side_effect = lambda key, default=None: {
        "DISCORD_TOKEN": "test_token",
        "SCHEDULED_REPORT_CHANNEL_IDS": [],
    }.get(key, default)

    result = GetSettings()

    assert result.scheduled_report_channel_ids == ()


@patch('src.core.dynaconf_settings.settings')
@patch('src.core.dynaconf_settings.os.environ.get')
def test_get_settings_defaults(mock_environ_get, mock_settings) -> None:
    """Test GetSettings with all defaults."""
    # Mock settings to return the default parameter when key doesn't exist
    def mock_get(key, default=None):
        # Return the default value to simulate missing keys
        return default

    mock_settings.get.side_effect = mock_get
    # Mock environment to return empty string for DISCORD_TOKEN
    mock_environ_get.return_value = ""

    result = GetSettings()

    assert result.discord_token == ""
    assert result.database_path == "bot.db"
    assert result.timezone == "America/New_York"
    assert result.use_db_only is False
    assert result.backfill_default_days == 30
    assert result.guild_id is None
    assert result.daily_goal_tasks == 5
    assert result.scheduled_reports_enabled is True
    assert result.scheduled_report_interval_minutes == 1
    assert result.scheduled_report_channel_ids == ()


@patch('src.core.dynaconf_settings.settings')
def test_get_settings_reload(mock_settings) -> None:
    """Test GetSettings with reload=True."""
    # Mock settings to return proper values
    def mock_get(key, default=None):
        if key == "DISCORD_TOKEN":
            return "test_token"
        return default

    mock_settings.get.side_effect = mock_get

    result = GetSettings(reload=True)

    mock_settings.reload.assert_called_once()
    assert result.discord_token == "test_token"


@patch('src.core.dynaconf_settings.settings')
def test_get_settings_exception_handling(mock_settings) -> None:
    """Test GetSettings exception handling."""
    mock_settings.get.side_effect = Exception("Test error")

    with pytest.raises(RuntimeError, match="Failed to load settings"):
        GetSettings()