"""Channel registration related commands."""

from typing import Any
import discord


def register_channel_commands(bot: Any, channels_service: Any) -> None:
    @bot.tree.command(name="register", description="Register current channel for habit tracking")
    async def register_channel(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        cid = interaction.channel_id
        if cid is None:
            await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
            return
        await channels_service.register(cid, interaction.user.id, None)
        await interaction.followup.send("Channel registered for habit tracking.")
        _ = register_channel
