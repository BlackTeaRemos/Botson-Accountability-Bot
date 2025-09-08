# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition


class ScheduleList(CommandDefinition):
    group_name = None
    group_description = ""

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        @group.command(name="list", description="List scheduled events for this channel")
        async def list_events(interaction: discord.Interaction):
            storage = ctx.get("storage")
            cid = interaction.channel_id
            if cid is None:
                await interaction.response.send_message("Must be used in a channel.", ephemeral=True)
                return
            try:
                events = storage.list_events(channel_discord_id=cid)
                if not events:
                    await interaction.response.send_message("No scheduled events found.", ephemeral=True)
                    return
                lines: list[str] = []
                for ev in events:
                    if ev.get('schedule_anchor') and ev.get('schedule_expr'):
                        lines.append(
                            f"ID {ev['id']}: anchor={ev['schedule_anchor']} expr={ev['schedule_expr']} -> '{ev['command']}' next at {ev['next_run']}"
                        )
                    else:
                        lines.append(
                            f"ID {ev['id']}: every {ev['interval_minutes']}m -> '{ev['command']}' next at {ev['next_run']}"
                        )
                body = "\n".join(lines)
                await interaction.response.send_message(f"Scheduled events:\n{body}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Error listing events: {e}", ephemeral=True)
