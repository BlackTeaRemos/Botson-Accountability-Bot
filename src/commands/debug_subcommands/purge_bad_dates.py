# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition
from ...services.persistence import PersistenceService


class DebugPurgeBadDates(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage: PersistenceService = ctx["storage"]

        @group.command(name="purge_bad_dates", description="Purge non-ISO date rows for this channel")
        async def _cmd(interaction: discord.Interaction):
            try:
                cid = interaction.channel_id
                if cid is None:
                    await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                    return
                if not storage.is_channel_registered(cid):
                    await interaction.response.send_message("Channel not registered.", ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True, thinking=True)
                deleted, _deleted_dates = storage.purge_non_iso_dates(cid)
                await interaction.followup.send(
                    f"Purge complete. Deleted {deleted} daily rows (and related per-message scores).",
                    ephemeral=True,
                )
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Purge failed: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Purge failed: {e}", ephemeral=True)
