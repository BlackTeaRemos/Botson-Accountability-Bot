# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition
from ...services.persistence import PersistenceService


class DebugUserInfo(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage: PersistenceService = ctx["storage"]

        @group.command(name="user_info", description="Show recent daily stats for a user")
        async def _cmd(interaction: discord.Interaction, user_id: str):
            try:
                cid = interaction.channel_id
                if cid is None:
                    await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                    return
                if not storage.is_channel_registered(cid):
                    await interaction.response.send_message("Channel not registered.", ephemeral=True)
                    return
                info = storage.debug_get_user_info(user_id=user_id, channel_discord_id=cid)
                if not info["days"]:
                    await interaction.response.send_message("No records.", ephemeral=True)
                    return
                lines = [
                    f"{d['date']}: raw={float(d.get('raw_score', 0.0)):.2f} msgs={int(d.get('messages', 0))}"
                    for d in info['days']
                ]
                total = info['total_raw']
                avg = info['avg_raw']
                body = "\n".join(lines)
                if len(body) > 1800:
                    body = body[:1800] + "..."
                await interaction.response.send_message(
                    f"User {user_id}\nTotal Raw: {total:.2f}\nAvg Raw: {avg:.2f}\nRecent (max 30 days):\n"
                    + body,
                    ephemeral=True,
                )
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Error: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Error: {e}", ephemeral=True)
