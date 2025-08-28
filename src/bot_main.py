"""Discord bot entrypoint: wires configuration, services, slash commands, and event handling."""

import discord
from discord.ext import commands
from datetime import datetime, timezone
from typing import Any, Dict, List
import random
from datetime import timedelta

from .core.config import load_config
from .db.migrations import ensure_migrated
from .db.connection import Database
from .core.events import EventBus
from .services.diagnostics import DiagnosticsService
from .services.channel_registration import ChannelRegistrationService
from .services.habit_parser import HabitParser
from .services.persistence import PersistenceService
from .services.reporting import ReportingService
from . import events
from .commands import reporting as reporting_commands
from .commands import debug as debug_commands
from .commands import channels as channel_commands
from .commands import utils as command_utils

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

config = load_config()
ensure_migrated(config.database_path)

db = Database(config.database_path)
bus = EventBus()

diagnostics = DiagnosticsService(bus, db, config.database_path)
channels = ChannelRegistrationService(bus, db, config.backfill_default_days)
habit_parser = HabitParser(bus)
storage = PersistenceService(db)
reporting = ReportingService(db, config)

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    """Called when the bot has successfully connected to Discord."""
    await bus.emit("BotStarted", {"user": str(bot.user)}, {})
    await diagnostics.run_startup()
    # Register slash commands from modules so they exist before syncing.
    register_bot_commands()
    try:
        # Always perform global sync so commands appear in every server the bot joins.
        global_synced = await bot.tree.sync()
        print(f"[Commands] Global sync -> {len(global_synced)} commands (global propagation may take up to ~1 hour)")
        # Optionally also push a guild-specific sync for immediate availability in a primary guild.
        if config.guild_id:
            guild = discord.Object(id=config.guild_id)
            guild_synced = await bot.tree.sync(guild=guild)
            print(f"[Commands] Guild sync ({config.guild_id}) -> {len(guild_synced)} commands (immediate)")
    except Exception as e:
        print(f"[Commands] Sync failed: {e}")


def register_bot_commands() -> None:
    """Register slash commands from external modules and inline diagnostics command.
    """
    # Module-registered commands
    reporting_commands.register_reporting_commands(bot, storage, reporting, channels, config)
    debug_commands.register_debug_commands(bot, storage, generate_random_user_recent)
    channel_commands.register_channel_commands(bot, channels)

    # Inline diagnostics command
    @bot.tree.command(name="diagnostics", description="Show basic diagnostics (db, counts, disk)")
    async def diagnostics_command(interaction: discord.Interaction):
        try:
            snapshot = diagnostics.collect()
            diagnostics_text = command_utils.json_dumps_compact(snapshot)
            if len(diagnostics_text) > 1800:
                diagnostics_text = diagnostics_text[:1800] + "... (truncated)"
            await interaction.response.send_message(f"```json\n{diagnostics_text}\n```", ephemeral=True)
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
    await bus.emit("MessageReceived", {
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
    await bus.emit("MessageEdited", {
        "discord_message_id": after.id,
        "channel_id": after.channel.id,
        "author_id": after.author.id,
        "author_display": after.author.display_name,
        "content": after.content,
        "created_at": after.created_at.isoformat(),
        "edited_at": datetime.now(tz=timezone.utc).isoformat(),
    }, {})
    # No command registration here — commands are registered at startup.


def run():
    """Main entry to launch the Discord bot after environment validation."""
    token = config.discord_token
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


def generate_random_user_recent(
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

def json_dumps_compact(data: Any) -> str:
    """Serialize data to deterministic compact JSON (stable key order).

    Args:
        data: The data to serialize.

    Returns:
        Compact JSON string with sorted keys.
    """
    import json
    return json.dumps(data, separators=(",", ":"), sort_keys=True)

if __name__ == "__main__":
    run()
