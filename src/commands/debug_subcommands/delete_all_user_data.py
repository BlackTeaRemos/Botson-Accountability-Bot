# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition
from ...services.persistence import PersistenceService


class DebugDeleteAllUserData(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage: PersistenceService = ctx["storage"]

        @group.command(name="delete_all_user_data", description="DELETE ALL user data from this channel (destructive!)")
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
                deleted_counts = storage.debug_delete_all_user_data(cid)
                total_deleted = sum(deleted_counts.values())

                if total_deleted == 0:
                    await interaction.followup.send(
                        "No user data found to delete.",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        f"WARNING: ALL USER DATA DELETED\n\n"
                        f"Successfully deleted ALL user data for this channel:\n"
                        f"• Messages: {deleted_counts['messages']}\n"
                        f"• Message scores: {deleted_counts['message_scores']}\n"
                        f"• Daily scores: {deleted_counts['daily_scores']}\n"
                        f"• **Total items deleted: {total_deleted}**\n\n"
                        f"**This action cannot be undone!**",
                        ephemeral=True,
                    )
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Error deleting user data: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Error deleting user data: {e}", ephemeral=True)
