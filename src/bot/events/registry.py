"""Registry for Discord bot event handlers.
"""
from __future__ import annotations

from typing import Callable
import discord
import logging
import os
from datetime import datetime, timezone

from .. import startup


def register_bot_events(bot: discord.Client) -> None:
    """Attach event handlers to the provided bot instance.
    """

    @bot.event
    async def on_ready() -> None:
        await startup.bus.Emit("BotStarted", {"user": str(bot.user)}, {})
        await startup.diagnostics.run_startup()

        # Register commands once
        if not getattr(bot, "_commands_registered_once", False):
            startup.RegisterBotCommands(bot)
            setattr(bot, "_commands_registered_once", True)

        try:
            guild_count = len(bot.guilds)
            global_synced = await bot.tree.sync()
            print(f"[Commands] Global sync -> {len(global_synced)} commands (joined guilds={guild_count}).")
            # One-time cleanup of legacy guild commands
            if not getattr(bot, "_guild_command_cleanup_done", False):
                cleared = 0
                for g in bot.guilds:
                    try:
                        guild_obj = discord.Object(id=g.id)  # type: ignore[arg-type]
                        bot.tree.clear_commands(guild=guild_obj)
                        await bot.tree.sync(guild=guild_obj)
                        cleared += 1
                        print(f"[Commands] Cleared legacy guild-specific commands for guild {g.id}.")
                    except Exception as guild_err:
                        print(f"[Commands] Guild cleanup failed for {g.id}: {guild_err}")
                setattr(bot, "_guild_command_cleanup_done", True)
                if cleared:
                    print(f"[Commands] Cleanup complete: cleared {cleared} guild command sets.")
        except Exception as e:
            print(f"[Commands] Sync failed: {e}")

        # Apply DB-backed overrides before starting scheduler
        try:
            await startup.UpdateRuntimeConfiguration(bot)
        except Exception as e:
            print(f"[Config] Failed to apply runtime settings on startup: {e}")

        raw_env = os.getenv('SCHEDULED_REPORTS_ENABLED')
        print(f"[Scheduler] Enabled setting: {startup.config.scheduled_reports_enabled}; env(SCHEDULED_REPORTS_ENABLED)={raw_env}")  # type: ignore
        if getattr(startup, "event_scheduler", None) is None:
            from src.services.event_scheduler import EventScheduler
            startup.event_scheduler = EventScheduler(bot, startup.storage)
            startup.event_scheduler.start()
            logging.getLogger("EventScheduler").info("Started custom event scheduler.")


    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        await startup.bus.Emit("MessageReceived", {
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
        if after.author.bot:
            return
        try:
            startup.storage.update_message_content(after.id, after.content)
        except Exception as e:
            print(f"[Edit] Failed to update content for {after.id}: {e}")
        await startup.bus.Emit("MessageEdited", {
            "discord_message_id": after.id,
            "channel_id": after.channel.id,
            "author_id": after.author.id,
            "author_display": after.author.display_name,
            "content": after.content,
            "created_at": after.created_at.isoformat(),
            "edited_at": datetime.now(tz=timezone.utc).isoformat(),
        }, {})

