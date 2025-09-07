"""Slash commands for user-defined scheduled events."""
from typing import Any
import discord
from discord import app_commands
from ..services.persistence import PersistenceService
from ..services.reporting import schedulable_reports  # add registry import


def RegisterScheduleCommands(bot: Any, storage: PersistenceService) -> None:
    """Register schedule slash commands."""
    schedule_group = app_commands.Group(name="schedule", description="Manage custom scheduled events")

    async def _safe_send(interaction: discord.Interaction, content: str, *, ephemeral: bool = True) -> None:
        """Send a response or followup safely depending on interaction state."""
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(content, ephemeral=ephemeral)
            else:
                await interaction.followup.send(content, ephemeral=ephemeral)
        except Exception:
            # As a last resort, try followup
            try:
                await interaction.followup.send(content, ephemeral=ephemeral)
            except Exception:
                pass

    @schedule_group.command(name="create", description="Create a new scheduled event")
    @app_commands.describe(report_type="Scheduled report type", interval_minutes="Time between events in minutes")
    async def CreateEvent(interaction: discord.Interaction, report_type: str, interval_minutes: int):
        # Defer early to avoid interaction timeout; use followups for final messages
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            # If already acknowledged by platform, continue with followup
            pass
        cid = interaction.channel_id
        if cid is None:
            await _safe_send(interaction, "Must be used in a channel.", ephemeral=True)
            return
        if not storage.is_channel_registered(cid):
            await _safe_send(interaction, "Channel not registered.", ephemeral=True)
            return
        try:
            if report_type not in schedulable_reports:
                await _safe_send(interaction, "Invalid report type.", ephemeral=True)
                return
            event_id = storage.add_event(channel_discord_id=cid, interval_minutes=interval_minutes, command=report_type)
            await interaction.followup.send(
                f"Scheduled event {event_id} created every {interval_minutes} minutes.",
                ephemeral=True,
            )
        except Exception as e:
            await _safe_send(interaction, f"Error creating event: {e}", ephemeral=True)
    @CreateEvent.autocomplete('report_type')
    async def report_type_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Suggest available scheduled report types."""
        suggestions = [
            app_commands.Choice(name=rt, value=rt)
            for rt in schedulable_reports
            if current.lower() in rt.lower()
        ]
        return suggestions[:25]

    @schedule_group.command(name="list", description="List scheduled events for this channel")
    async def ListEvents(interaction: discord.Interaction):
        cid = interaction.channel_id
        if cid is None:
            await interaction.response.send_message("Must be used in a channel.", ephemeral=True)
            return
        try:
            events = storage.list_events(channel_discord_id=cid)
            if not events:
                await interaction.response.send_message("No scheduled events found.", ephemeral=True)
                return
            lines = []
            for ev in events:
                lines.append(f"ID {ev['id']}: every {ev['interval_minutes']}m -> '{ev['command']}' next at {ev['next_run']}")
            body = "\n".join(lines)
            await interaction.response.send_message(f"Scheduled events:\n{body}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error listing events: {e}", ephemeral=True)

    @schedule_group.command(name="remove", description="Remove a scheduled event by ID")
    async def RemoveEvent(interaction: discord.Interaction, event_id: int):
        try:
            success = storage.remove_event(event_id=event_id)
            if success:
                await interaction.response.send_message(f"Scheduled event {event_id} removed.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Event {event_id} not found.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error removing event: {e}", ephemeral=True)

    bot.tree.add_command(schedule_group)
