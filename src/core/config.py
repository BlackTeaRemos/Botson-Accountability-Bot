import os
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class AppConfig:
    """Configuration for the Discord bot application.

    Attributes:
        discord_token: The Discord bot token from environment.
        database_path: Path to the SQLite database file.
        timezone: Timezone string for date calculations.
        use_db_only: Whether to use database only mode.
        backfill_default_days: Default days for backfilling data.
        guild_id: Optional guild ID for faster command sync.
        daily_goal_tasks: Target tasks per day for full score.
        scheduled_reports_enabled: Whether background scheduled reports are enabled.
        scheduled_report_interval_minutes: Minutes between scheduled report posts.
        scheduled_report_channel_ids: Optional explicit channel id list to post into; if empty, use all registered.
    """
    # TODO: that's obviously requires rework into configuration
    discord_token: str
    database_path: str = "bot.db"
    timezone: str = "America/New_York"
    use_db_only: bool = False
    backfill_default_days: int = 30
    guild_id: Optional[int] = None  # optional for faster command sync
    daily_goal_tasks: int = 5  # target tasks (filled brackets) per day for full score
    scheduled_reports_enabled: bool = True
    scheduled_report_interval_minutes: int = 1
    scheduled_report_channel_ids: tuple[int, ...] = tuple()


def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Returns:
        AppConfig instance with loaded values.
    """
    token = os.getenv("DISCORD_TOKEN", "")
    
    def _getenv_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        return raw.strip().lower() in ("1", "true", "yes", "on")
    # Parse optional CSV of channel ids
    channels_csv = os.getenv("SCHEDULED_REPORT_CHANNEL_IDS", "").strip()
    channel_ids: tuple[int, ...] = tuple(
        int(x) for x in channels_csv.split(",") if x.strip().isdigit()
    ) if channels_csv else tuple()

    return AppConfig(
        discord_token=token,
        database_path=os.getenv("BOT_DB_PATH", "bot.db"),
        timezone=os.getenv("BOT_TZ", "America/New_York"),
        use_db_only=os.getenv("USE_DB_ONLY", "false").lower() == "true",
        backfill_default_days=int(os.getenv("BACKFILL_DEFAULT_DAYS", "30")),
        guild_id=int(os.getenv("GUILD_ID", "0")) or None,
        daily_goal_tasks=int(os.getenv("DAILY_GOAL_TASKS", "5")),
        # Default to True if not provided so the scheduler runs out-of-the-box
        scheduled_reports_enabled=_getenv_bool("SCHEDULED_REPORTS_ENABLED", True),
        scheduled_report_interval_minutes=int(os.getenv("SCHEDULED_REPORT_INTERVAL_MINUTES", "1")),
        scheduled_report_channel_ids=channel_ids,
    )
