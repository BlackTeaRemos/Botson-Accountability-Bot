"""Helpers to start and configure the Discord bot.

This module centralizes functionality that was previously defined in
`src.bot_main.py` so the entrypoint can remain small and focused.
"""

from datetime import datetime, timezone
from typing import Any
import os
import discord

from src.computeConfig import _ComputeOverriddenConfig

from ..core.config import LoadConfig  # type: ignore
from ..db.migrations import EnsureMigrated
from ..db.connection import Database
from ..core.events import EventBus
from ..services.diagnostics import DiagnosticsService
from ..services.channel_registration import ChannelRegistrationService
from ..services.habit_parser import HabitParser
from ..services.persistence import PersistenceService
from ..services.reporting import ReportingService
from ..services.settings import SettingsService
from ..commands import reporting as reporting_commands
from ..commands import debug as debug_commands
from ..commands import channels as channel_commands
from ..commands import debug_functions as debug_functions
from ..commands import utils as command_utils


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
event_scheduler: object | None = None


async def UpdateRuntimeConfiguration(bot: discord.Client) -> None:
    """Reload config overrides from DB and apply to running services.
    """
    global config, reporting, report_scheduler
    new_config = _ComputeOverriddenConfig(config)
    config = new_config
    reporting.config = new_config


def RegisterBotCommands(bot: discord.Client) -> None:
    """Register slash commands from modules and add inline diagnostics command.
    """
    # Module-registered commands
    reporting_commands.ReportingCommands.register_with_services(bot, storage, reporting, channels, config)  # type: ignore
    debug_commands.DebugCommands.register_with_services(bot, storage, debug_functions.make_generate_random_user_recent(storage))
    channel_commands.RegisterChannelCommands(bot, channels)

    # Register user-defined schedule and reminder commands
    from ..commands.schedule_event import ScheduleCommands

    ScheduleCommands.register_with_services(bot, storage)
    try:
        from ..commands.reminder import RegisterReminderCommands  # type: ignore

        RegisterReminderCommands(bot, storage)
    except Exception:
        # Reminder registration optional
        pass

    # Inline diagnostics command
    @bot.tree.command(name="diagnostics", description="Show basic diagnostics (db, counts, disk)")
    async def diagnostics_command(interaction: discord.Interaction):
        try:
            snapshot = diagnostics.collect()
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


def JsonDumpsCompact(data: Any) -> str:
    """Serialize data to deterministic compact JSON (stable key order)."""
    import json

    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def Run(bot: discord.Client) -> None:
    """Run the provided bot instance using the loaded config.

    This keeps behaviour compatible with the previous `Run()` function but
    accepts a bot instance so tests or alternate runners can provide their own
    object.
    """
    token = config.discord_token  # type: ignore
    token_parts = token.split('.')
    masked_token = token_parts[0][:4] + "..." + token_parts[-1][-4:]
    print(f"[Startup] Using token (masked): {masked_token}")

    try:
        RegisterRuntime(bot)
    except Exception:
        import traceback

        print("[Startup] RegisterRuntime failed:")
        traceback.print_exc()

    bot.run(token)


def RegisterRuntime(bot: discord.Client) -> None:
    """Register runtime integrations for the bot.
    """
    from .. import events as events_module
    events_module.register_message_ingestion(bus, storage, habit_parser)

    try:
        RegisterBotCommands(bot)
        setattr(bot, "_commands_registered_once", True)
    except Exception as e:
        import traceback

        print(f"[Startup] RegisterBotCommands failed: {e}")
        traceback.print_exc()
    else:
        try:
            import asyncio
            import traceback as _tb

            async def _sync_tree():
                try:
                    synced = await bot.tree.sync()
                    print(f"[Startup] Early background sync complete -> {len(synced)} commands")
                except Exception as _e:
                    print("[Startup] Early background sync failed:")
                    _tb.print_exc()

            try:
                bot.loop.create_task(_sync_tree())
            except Exception:
                asyncio.create_task(_sync_tree())
        except Exception:
            pass

    from .events import registry as bot_event_registry
    bot_event_registry.register_bot_events(bot)
