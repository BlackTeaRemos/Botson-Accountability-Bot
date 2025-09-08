# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition


class ScheduleRemove(CommandDefinition):
    group_name = None
    group_description = ""

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage = ctx.get("storage")

        @group.command(name="remove", description="Remove a scheduled event by ID")
        async def remove_event(interaction: discord.Interaction, event_id: int):
            try:
                success = storage.remove_event(event_id=event_id)
                if success:
                    await interaction.response.send_message(f"Scheduled event {event_id} removed.", ephemeral=True)
                else:
                    await interaction.response.send_message(f"Event {event_id} not found.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Error removing event: {e}", ephemeral=True)
