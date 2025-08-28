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
    """
    # TODO: that's obviously requires rework into configuration
    discord_token: str
    database_path: str = "bot.db"
    timezone: str = "America/New_York"
    use_db_only: bool = False
    backfill_default_days: int = 30
    guild_id: Optional[int] = None  # optional for faster command sync
    daily_goal_tasks: int = 5  # target tasks (filled brackets) per day for full score


def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Returns:
        AppConfig instance with loaded values.
    """
    token = os.getenv("DISCORD_TOKEN", "")
    return AppConfig(
        discord_token=token,
        database_path=os.getenv("BOT_DB_PATH", "bot.db"),
        timezone=os.getenv("BOT_TZ", "America/New_York"),
        use_db_only=os.getenv("USE_DB_ONLY", "false").lower() == "true",
        backfill_default_days=int(os.getenv("BACKFILL_DEFAULT_DAYS", "30")),
        guild_id=int(os.getenv("GUILD_ID", "0")) or None,
        daily_goal_tasks=int(os.getenv("DAILY_GOAL_TASKS", "5")),
    )
