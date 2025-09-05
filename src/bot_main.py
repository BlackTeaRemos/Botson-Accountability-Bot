"""Discord bot entrypoint: wires configuration, services, slash commands, and event handling."""

import discord
from discord.ext import commands
from datetime import datetime, timezone
from typing import Any, Dict, List
import random
from datetime import timedelta

from .core.config import LoadConfig, AppConfig  # type: ignore
from .db.migrations import EnsureMigrated
from .db.connection import Database
from .core.events import EventBus
from .services.diagnostics import DiagnosticsService
from .services.channel_registration import ChannelRegistrationService
from .services.habit_parser import HabitParser
from .services.persistence import PersistenceService
from .services.reporting import ReportingService
from .services.settings import SettingsService
from . import events
from .commands import reporting as reporting_commands
from .commands import debug as debug_commands
from .commands import channels as channel_commands
from .commands import config as config_commands
from .commands import utils as command_utils
from .commands import config as config_commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

config = LoadConfig()  # type: ignore
EnsureMigrated(config.database_path)  # type: ignore

db = Database(config.database_path)  # type: ignore
bus = EventBus()

diagnostics = DiagnosticsService(bus, db, config.database_path)  # type: ignore
channels = ChannelRegistrationService(bus, db, config.backfill_default_days)  # type: ignore
habit_parser = HabitParser(bus)
storage = PersistenceService(db)
reporting = ReportingService(db, config)  # type: ignore
settings = SettingsService(db)
report_scheduler: object | None = None

bot = commands.Bot(command_prefix="!", intents=intents)


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


async def ApplyRuntimeSettings() -> None:
    """Reload config overrides from DB and apply to running services.

    This function reloads configuration settings from the database and applies them
    to running services without restarting the bot. It updates the reporting service
    configuration and restarts or stops the report scheduler based on the new settings.

    Args:
        None

    Returns:
        None

    Raises:
        No exceptions raised; errors are logged and the function continues

    Example:
        await ApplyRuntimeSettings()  # Reload and apply DB config settings
    """
    global config, reporting, report_scheduler
    new_config = _ComputeOverriddenConfig(config)
    config = new_config
    # Propagate to services
    reporting.config = new_config
    # Restart scheduler according to new settings
    try:
        if new_config.scheduled_reports_enabled:  # type: ignore

            if report_scheduler is None:
                from .services.scheduler import ReportScheduler  # type: ignore
                report_scheduler = ReportScheduler(bot, storage, reporting, new_config)  # type: ignore[assignment]
                report_scheduler.start()  # type: ignore[attr-defined]
            else:
                # Replace config inside scheduler
                try:
                    report_scheduler.config = new_config  # type: ignore[attr-defined]
                except Exception:
                    pass
        else:
            if report_scheduler is not None:
                try:
                    await report_scheduler.stop()  # type: ignore[attr-defined]
                except Exception:
                    pass
                report_scheduler = None
    except Exception as e:
        print(f"[Config] Failed to apply scheduler settings: {e}")


@bot.event
async def on_ready() -> None:
    """Called when the bot has successfully connected to Discord."""
    await bus.Emit("BotStarted", {"user": str(bot.user)}, {})
    await diagnostics.run_startup()
    # Register slash commands from modules so they exist before syncing.
    RegisterBotCommands()
    try:
        # Always perform global sync so commands appear in every server the bot joins.
        global_synced = await bot.tree.sync()
        print(f"[Commands] Global sync -> {len(global_synced)} commands (global propagation may take up to ~1 hour)")
        # If the bot is in a small number of guilds (<5), perform per-guild sync for immediate availability.
        guild_count = len(bot.guilds)
        if guild_count < 5:
            synced_total = 0
            for g in bot.guilds:
                try:
                    guild_obj = discord.Object(id=g.id)  # type: ignore[arg-type]
                    # Copy global commands into the guild scope for instant availability, then sync
                    try:
                        bot.tree.copy_global_to(guild=guild_obj)
                    except Exception:
                        # Safe to ignore; copy is best-effort
                        pass
                    guild_synced = await bot.tree.sync(guild=guild_obj)
                    synced_total += len(guild_synced)
                    print(f"[Commands] Guild sync ({g.id}) -> {len(guild_synced)} commands (immediate)")
                except Exception as guild_err:
                    print(f"[Commands] Guild sync failed for {g.id}: {guild_err}")
        else:
            print(f"[Commands] Skipping per-guild sync (joined guilds={guild_count}); relying on global propagation.")
    except Exception as e:
        print(f"[Commands] Sync failed: {e}")
    # Apply any DB-backed overrides before starting scheduler
    try:
        await ApplyRuntimeSettings()
    except Exception as e:
        print(f"[Config] Failed to apply runtime settings on startup: {e}")
    # Start scheduled reports if enabled
    global report_scheduler
    import os
    raw_env = os.getenv('SCHEDULED_REPORTS_ENABLED')
    print(f"[Scheduler] Enabled setting: {config.scheduled_reports_enabled}; env(SCHEDULED_REPORTS_ENABLED)={raw_env}")  # type: ignore
    if config.scheduled_reports_enabled:  # type: ignore
        if report_scheduler is None:
            # Lazy import to avoid optional dependency/type-resolution noise
            from .services.scheduler import ReportScheduler  # type: ignore
            report_scheduler = ReportScheduler(bot, storage, reporting, config)  # type: ignore[assignment]
            report_scheduler.start()  # type: ignore[attr-defined]
            print(
                f"[Scheduler] Started (interval={config.scheduled_report_interval_minutes}m, "  # type: ignore
                f"channels={list(config.scheduled_report_channel_ids) if config.scheduled_report_channel_ids else 'all-registered'})"  # type: ignore
            )
    else:
        print("[Scheduler] Disabled by configuration; not started.")


def RegisterBotCommands() -> None:
    """Register slash commands from external modules and inline diagnostics command.

    This function registers all Discord slash commands by calling the registration
    functions from the command modules and adding an inline diagnostics command.

    The registered commands include:
    - Reporting commands for habit tracking reports
    - Debug commands for testing and maintenance
    - Channel commands for channel management
    - Config commands for bot configuration
    - Inline diagnostics command for system status

    Args:
        None

    Returns:
        None

    Example:
        RegisterBotCommands()  # Registers all bot commands
    """
    # Module-registered commands
    reporting_commands.RegisterReportingCommands(bot, storage, reporting, channels, config)  # type: ignore
    debug_commands.RegisterDebugCommands(bot, storage, GenerateRandomUserRecent)
    channel_commands.RegisterChannelCommands(bot, channels)
    config_commands.RegisterConfigCommands(bot, settings, ApplyRuntimeSettings)

    # Inline diagnostics command
    @bot.tree.command(name="diagnostics", description="Show basic diagnostics (db, counts, disk)")
    async def diagnostics_command(interaction: discord.Interaction):
        try:
            snapshot = diagnostics.collect()
            # Prefer a readable summary; if too long, fall back to compact JSON
            readable = command_utils.FormatDiagnosticsMarkdown(snapshot)
            content: str
            if len(readable) <= 1900:
                content = f"```\n{readable}\n```"
            else:
                json_text = command_utils.JsonDumpsCompact(snapshot)
                if len(json_text) > 1900:
                    json_text = json_text[:1900] + "... (truncated)"
                content = f"```json\n{json_text}\n```"
            await interaction.response.send_message(content, ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Diagnostics error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Diagnostics error: {e}", ephemeral=True)
    # Mark used for static analysis
    _ = diagnostics_command


@bot.event
async def on_message(message: discord.Message) -> None:
    """Called when a message is received. Ignores bot messages and emits an event."""
    if message.author.bot:
        return
    await bus.Emit("MessageReceived", {
        "discord_message_id": message.id,
        "channel_id": message.channel.id,
        "author_id": message.author.id,
        "author_display": message.author.display_name,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }, {})
    await bot.process_commands(message)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
    """Called when a message is edited. Updates stored content and re-emits as edited event."""
    if after.author.bot:
        return
    # Update stored content then re-emit as edited event for parsing path.
    try:
        storage.update_message_content(after.id, after.content)
    except Exception as e:
        print(f"[Edit] Failed to update content for {after.id}: {e}")
    await bus.Emit("MessageEdited", {
        "discord_message_id": after.id,
        "channel_id": after.channel.id,
        "author_id": after.author.id,
        "author_display": after.author.display_name,
        "content": after.content,
        "created_at": after.created_at.isoformat(),
        "edited_at": datetime.now(tz=timezone.utc).isoformat(),
    }, {})
    # No command registration here — commands are registered at startup.


def Run():
    """Main entry to launch the Discord bot after environment validation.

    This function performs the following steps:
    1. Validates the Discord token from configuration
    2. Registers event handlers for message ingestion
    3. Starts the Discord bot with the validated token

    Raises:
        SystemExit: If the Discord token is not properly configured

    Example:
        Run()  # Launches the bot if token is valid
    """
    token = config.discord_token  # type: ignore
    if not token or token == "" or token.lower() == "changeme":
        raise SystemExit("DISCORD_TOKEN not set in environment")

    token_parts = token.split('.')
    if len(token_parts) != 3:
        raise SystemExit(
            "DISCORD_TOKEN format unexpected (should contain 2 dots). "
            "Double-check the bot token, not client secret or application ID."
        )
    masked_token = token_parts[0][:4] + "..." + token_parts[-1][-4:]
    print(f"[Startup] Using token (masked): {masked_token}")

    events.register_message_ingestion(bus, storage, habit_parser)
    bot.run(token)


def GenerateRandomUserRecent(
    channel_discord_id: int,
    user_id: str | None = None,
    messages: int = 5,
    within_days: int = 7,
    cluster_days: int = 1,
    jitter_minutes: int = 120,
    dry_run: bool = False,
)-> Dict[str, Any]:
    """Generate a random user with multiple habit entries clustered near each other in the recent week.

    Args:
        channel_discord_id: Discord channel id where messages would be recorded.
        user_id: Optional user id to use; if None a random string id is created.
        messages: Number of message entries to generate.
        within_days: How many days back to allow (0..within_days-1) for the cluster center.
        cluster_days: How many adjacent days the generated entries may span (1 = same day).
        jitter_minutes: Max minutes of jitter around the center time for each message.
        dry_run: If True, do not call persistence methods; return generated payload instead.

    Returns:
        dict with keys: user_id, messages (list of generated payloads), written (bool).
    """
    # Prepare user id
    if user_id is None:
        user_id = f"testuser_{random.randint(1000, 9999)}"

    now = datetime.now(tz=timezone.utc)
    # pick a cluster center day within the allowed range
    days_back = random.randint(0, max(0, within_days - 1))
    center_date = (now - timedelta(days=days_back)).date()

    generated: List[Dict[str, Any]] = []
    for message_index in range(messages):
        # Choose a day within the cluster (0..cluster_days-1) anchored at center_date
        day_offset = random.randint(0, max(0, cluster_days - 1))
        entry_date = center_date - timedelta(days=day_offset)
        # Choose a time near midday for readability then add jitter
        base_dt = datetime.combine(entry_date, datetime.min.time()) + timedelta(hours=12)
        minute_jitter = random.randint(-jitter_minutes, jitter_minutes)
        created_at = base_dt + timedelta(
            minutes=minute_jitter + message_index
        )  # spread slightly across messages
        discord_message_id = random.randint(10**16, 10**18 - 1)
        extracted_date = entry_date.isoformat()
        payload: Dict[str, Any] = {
            "discord_message_id": discord_message_id,
            "channel_id": channel_discord_id,
            "author_id": str(user_id),
            "author_display": str(user_id),
            "content": "[x] Habit entry (generated)",
            "created_at": created_at.isoformat(),
            "extracted_date": extracted_date,
        }
        generated.append(payload)

    if dry_run:
        return {"user_id": user_id, "messages": generated, "written": False}

    # Ensure channel exists
    if not storage.is_channel_registered(channel_discord_id):
        raise ValueError(f"Channel {channel_discord_id} not registered. Register channel before writing test data.")

    # Insert into DB using persistence helpers
    dates_used: set[str] = set()
    for message_payload in generated:
        storage.insert_message(
            discord_message_id=message_payload["discord_message_id"],
            channel_id=message_payload["channel_id"],
            author_id=message_payload["author_id"],
            author_display=message_payload["author_display"],
            created_at=message_payload["created_at"],
            content=message_payload["content"],
        )
        # Persist a simple parse and per-message score (raw_ratio=1.0 -> counts as one)
        storage.update_habit_parse(
            message_payload["discord_message_id"],
            raw_bracket_count=1,
            filled_bracket_count=1,
            confidence=0.9,
            extracted_date=message_payload["extracted_date"]
        )
        storage.insert_or_replace_message_score(
            discord_message_id=message_payload["discord_message_id"],
            user_id=message_payload["author_id"],
            date=message_payload["extracted_date"],
            channel_discord_id=message_payload["channel_id"],
            raw_ratio=1.0,
            filled=1,
            total=1,
        )
        dates_used.add(message_payload["extracted_date"])

    # Recompute daily aggregates for the dates we touched
    for date_string in dates_used:
        storage.recompute_daily_scores(channel_discord_id=channel_discord_id, date=date_string)

    return {"user_id": user_id, "messages": generated, "written": True}

def JsonDumpsCompact(data: Any) -> str:
    """Serialize data to deterministic compact JSON (stable key order).

    Args:
        data: The data to serialize.

    Returns:
        Compact JSON string with sorted keys.
    """
    import json
    return json.dumps(data, separators=(",", ":"), sort_keys=True)

if __name__ == "__main__":
    Run()
