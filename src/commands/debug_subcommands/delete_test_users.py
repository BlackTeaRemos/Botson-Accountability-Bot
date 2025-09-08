# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition
from ...services.persistence import PersistenceService


class DebugDeleteTestUsers(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage: PersistenceService = ctx["storage"]

        @group.command(name="delete_test_users", description="Delete all test user data from this channel")
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
                deleted_counts = storage.debug_delete_test_users(cid)
                total_deleted = sum(deleted_counts.values())

                if total_deleted == 0:
                    await interaction.followup.send(
                        "No test user data found to delete.",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        f"Successfully deleted test user data:\n"
                        f"• Messages: {deleted_counts['messages']}\n"
                        f"• Message scores: {deleted_counts['message_scores']}\n"
                        f"• Daily scores: {deleted_counts['daily_scores']}\n"
                        f"• Total items: {total_deleted}",
                        ephemeral=True,
                    )
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Error deleting test users: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Error deleting test users: {e}", ephemeral=True)
