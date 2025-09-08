from src.core.config import AppConfig


def _ComputeOverriddenConfig(base: AppConfig) -> AppConfig:  # type: ignore
    """Overlay DB settings onto the base config (excluding token).

    This function reads configuration settings from the database and overlays them
    onto the base configuration loaded from files/environment. The token is never
    stored in or read from the database for security reasons.

    Args:
        base: The base AppConfig loaded from files and environment variables

    Returns:
        AppConfig: A new AppConfig instance with DB settings overlaid on the base

    Raises:
        No exceptions raised; invalid DB values fall back to base config defaults

    Example:
        new_config = _ComputeOverriddenConfig(base_config)
        # new_config.timezone will be from DB if set, otherwise base_config.timezone
    """

    from dataclasses import replace
    from src.bot.startup import settings
    # Gather overrides
    tz = settings.get("timezone")
    use_db_only = settings.get("use_db_only")
    backfill_days = settings.get("backfill_default_days")
    guild_id = settings.get("guild_id")
    daily_goal = settings.get("daily_goal_tasks")
    sched_enabled = settings.get("scheduled_reports_enabled")
    sched_interval = settings.get("scheduled_report_interval_minutes")
    sched_channels = settings.get("scheduled_report_channel_ids")

    def as_int(val: object, default: int) -> int:
        try:
            if isinstance(val, bool):
                return int(val)
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, str):
                return int(val.strip())
        except Exception:
            return default
        return default

    def as_bool(val: object, default: bool) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return bool(val)
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return default

    from typing import Any, Iterable, cast
    def as_tuple_ints(val: Any, default: tuple[int, ...]) -> tuple[int, ...]:
        try:
            if val is None:
                return default
            if isinstance(val, (list, tuple)):
                out: list[int] = []
                it: Iterable[Any] = cast(Iterable[Any], val)
                for item in it:
                    try:
                        out.append(int(str(item)))
                    except Exception:
                        continue
                return tuple(out)
            if isinstance(val, str):
                # accept CSV string
                parts = [p.strip() for p in val.split(',') if p.strip()]
                return tuple(int(p) for p in parts if p.isdigit())
        except Exception:
            return default
        return default

    cfg = replace(  # type: ignore
        base,  # type: ignore
        timezone=str(tz) if isinstance(tz, str) and tz else base.timezone,  # type: ignore
        use_db_only=as_bool(use_db_only, base.use_db_only),  # type: ignore
        backfill_default_days=as_int(backfill_days, base.backfill_default_days),  # type: ignore
        guild_id=as_int(guild_id, base.guild_id or 0) or None,  # type: ignore
        daily_goal_tasks=as_int(daily_goal, base.daily_goal_tasks),  # type: ignore
        scheduled_reports_enabled=as_bool(sched_enabled, base.scheduled_reports_enabled),  # type: ignore
        scheduled_report_interval_minutes=as_int(sched_interval, base.scheduled_report_interval_minutes),  # type: ignore
        scheduled_report_channel_ids=as_tuple_ints(sched_channels, base.scheduled_report_channel_ids),  # type: ignore
    )
    
    return cfg  # type: ignore