# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition
from ...services.persistence import PersistenceService


class DebugDeleteAllReports(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage: PersistenceService = ctx["storage"]

        @group.command(name="delete_all_reports", description="Delete all reports from the database")
        async def _cmd(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True, thinking=True)
                deleted_count = storage.debug_delete_all_reports()
                await interaction.followup.send(
                    f"Successfully deleted {deleted_count} reports from the database.",
                    ephemeral=True,
                )
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Error deleting reports: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Error deleting reports: {e}", ephemeral=True)
