# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition
from ...services.persistence import PersistenceService


class DebugAddScore(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage: PersistenceService = ctx["storage"]

        @group.command(name="add_score", description="Add raw score delta to user for a date")
        async def _cmd(interaction: discord.Interaction, user_id: str, date: str, delta: float):
            try:
                cid = interaction.channel_id
                if cid is None:
                    await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                    return
                if not storage.is_channel_registered(cid):
                    await interaction.response.send_message("Channel not registered.", ephemeral=True)
                    return
                storage.debug_add_score(user_id=user_id, date=date, channel_discord_id=cid, delta=delta)
                await interaction.response.send_message(f"Added {delta} raw to {user_id} on {date}.", ephemeral=True)
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Error: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Error: {e}", ephemeral=True)
