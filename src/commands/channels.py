"""Channel registration related commands, grouped under /channel."""

from typing import Any
import discord
from discord import app_commands


def register_channel_commands(bot: Any, channels_service: Any) -> None:
    channel_group = app_commands.Group(name="channel", description="Channel management")

    @channel_group.command(name="register", description="Register current channel for habit tracking")
    async def register_channel(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        cid = interaction.channel_id
        if cid is None:
            await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
            return
        await channels_service.register(cid, interaction.user.id, None)
        await interaction.followup.send("Channel registered for habit tracking.")

    bot.tree.add_command(channel_group)

    # Keep references for analyzers
    _registered_channel_cmds: dict[str, object] = {"register": register_channel}
    _ = _registered_channel_cmds
