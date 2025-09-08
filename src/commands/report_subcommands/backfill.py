# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition


class ReportBackfill(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage = ctx["storage"]
        channels = ctx["channels"]

        @group.command(name="backfill", description="Backfill last 7 days of messages for this channel")
        async def _cmd(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True, thinking=True)
                channel_id = interaction.channel_id
                if channel_id is None:
                    await interaction.followup.send("This command must be used in a channel.")
                    return
                if not storage.is_channel_registered(channel_id):
                    await interaction.followup.send("Channel not registered.")
                    return
                channel = interaction.channel
                if not isinstance(channel, discord.TextChannel):
                    await interaction.followup.send("Not a text channel.")
                    return
                messages_fetched = await channels.backfill_recent(channel, days=7)
                await interaction.followup.send(f"Backfill complete. Processed {messages_fetched} messages.")
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Backfill failed: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Backfill failed: {e}", ephemeral=True)
