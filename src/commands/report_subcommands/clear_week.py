# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition


class ReportClearWeek(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage = ctx["storage"]

        @group.command(name="clear_week", description="Clear current week's daily scores for this channel")
        async def _cmd(interaction: discord.Interaction):
            try:
                channel_id = interaction.channel_id
                if channel_id is None:
                    await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                    return
                if not storage.is_channel_registered(channel_id):
                    await interaction.response.send_message("Channel not registered.", ephemeral=True)
                    return
                deleted_rows = storage.clear_current_week_scores(channel_id)
                await interaction.response.send_message(
                    f"Cleared {deleted_rows} daily score rows for current week.", ephemeral=True
                )
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Clear failed: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Clear failed: {e}", ephemeral=True)
