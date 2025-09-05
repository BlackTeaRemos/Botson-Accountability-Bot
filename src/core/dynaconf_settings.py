from dataclasses import dataclass
from typing import Optional, Tuple, Any
import os

from dynaconf import Dynaconf  # type: ignore

settings: Dynaconf = Dynaconf(  # type: ignore
    settings_files=["settings.toml", ".secrets.toml"],
    environments=True,           # allow [default], [development], [production], [testing]
    envvar_prefix="BOT",         # env vars like BOT_DB_PATH etc.
    load_dotenv=True,            # read .env file if present
    env_switcher="DYNACONF_ENV", # switch env with DYNACONF_ENV=testing
)


@dataclass(frozen=True)
class AppConfig:
    """Configuration class holding all application settings.

    This dataclass contains the parsed and validated configuration values
    loaded from settings files, environment variables, and defaults.
    """
    discord_token: str  # The Discord bot authentication token
    database_path: str = "bot.db"  # Path to the SQLite database file
    timezone: str = "America/New_York"  # Timezone for scheduling and reports
    use_db_only: bool = False  # Whether to use database only mode
    backfill_default_days: int = 30  # Default days for backfilling data
    guild_id: Optional[int] = None  # Discord guild/server ID
    daily_goal_tasks: int = 5  # Number of daily goal tasks
    scheduled_reports_enabled: bool = True  # Enable scheduled reports
    scheduled_report_interval_minutes: int = 1  # Interval for scheduled reports in minutes
    scheduled_report_channel_ids: Tuple[int, ...] = tuple()  # Channel IDs for scheduled reports


def _ParseChannelIds(value: Optional[Any]) -> Tuple[int, ...]:
    """Parse channel IDs from various input formats.

    Args:
        value: Input value that can be None, list, tuple, or CSV string.

    Returns:
        Tuple[int, ...]: Parsed channel IDs as integers.

    Example:
        _ParseChannelIds("123,456") -> (123, 456)
        _ParseChannelIds([123, 456]) -> (123, 456)
    """
    if value is None:
        return tuple()
    if isinstance(value, (list, tuple)):
        return tuple(int(x) for x in value)  # type: ignore
    # allow CSV
    return tuple(int(x.strip()) for x in str(value).split(",") if x.strip())  # type: ignore


def GetSettings(reload: bool = False) -> AppConfig:
    """
    Return AppConfig built from Dynaconf's settings.

    Args:
        reload: Whether to reload files and environment (useful in tests). Defaults to False.

    Returns:
        AppConfig: Configuration instance with loaded values.

    Example:
        config = GetSettings()
        config = GetSettings(reload=True)  # Reload settings
    """
    try:
        if reload:
            settings.reload()  # type: ignore

        # Prefer value from settings files; if absent, fall back to unprefixed OS env DISCORD_TOKEN
        token_from_settings: Any = settings.get("DISCORD_TOKEN", None)  # type: ignore[arg-type]
        if token_from_settings in (None, ""):
            token_env = os.environ.get("DISCORD_TOKEN", "")
            token: str = str(token_env)
        else:
            if isinstance(token_from_settings, str):
                token = token_from_settings
            else:
                # Explicit cast to appease type checkers when dynaconf returns Any/Unknown
                token = "" if token_from_settings in (None, "") else f"{token_from_settings}"

        guild_id_raw = settings.get("GUILD_ID", None)  # type: ignore
        guild_id = int(guild_id_raw) if guild_id_raw not in (None, "", 0) else None  # type: ignore

        return AppConfig(
            discord_token=token,
            database_path=settings.get("DB_PATH", settings.get("BOT_DB_PATH", "bot.db")),  # type: ignore
            timezone=settings.get("BOT_TZ", "America/New_York"),  # type: ignore
            use_db_only=bool(settings.get("USE_DB_ONLY", False)),  # type: ignore
            backfill_default_days=int(settings.get("BACKFILL_DEFAULT_DAYS", 30)),  # type: ignore
            guild_id=guild_id,
            daily_goal_tasks=int(settings.get("DAILY_GOAL_TASKS", 5)),  # type: ignore
            scheduled_reports_enabled=bool(settings.get("SCHEDULED_REPORTS_ENABLED", True)),  # type: ignore
            scheduled_report_interval_minutes=int(
                settings.get("SCHEDULED_REPORT_INTERVAL_MINUTES", 1)  # type: ignore
            ),
            scheduled_report_channel_ids=_ParseChannelIds(
                settings.get("SCHEDULED_REPORT_CHANNEL_IDS", [])  # type: ignore
            ),
        )
    except Exception as e:
        raise RuntimeError(f"Failed to load settings: {e}") from e