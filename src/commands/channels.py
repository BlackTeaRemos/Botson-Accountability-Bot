"""Channel registration related commands."""

from typing import Any
import discord


def RegisterChannelCommands(bot: Any, channels_service: Any) -> None:
    """Register channel management commands on the bot.

    Args:
        bot: The Discord bot instance to register commands on.
        channels_service: The channel registration service instance.

    Returns:
        None

    Example:
        RegisterChannelCommands(bot, channels_service)
    """
    channel_group = app_commands.Group(name="channel", description="Channel management")

    @channel_group.command(name="register", description="Register current channel for habit tracking")
    async def RegisterChannel(interaction: discord.Interaction):
        """Register the current channel for habit tracking.

        Args:
            interaction: The Discord interaction object.

        Returns:
            None
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        cid = interaction.channel_id
        if cid is None:
            await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
            return
        await channels_service.register(cid, interaction.user.id, None)
        await interaction.followup.send("Channel registered for habit tracking.")

    bot.tree.add_command(channel_group)

    # Keep references for analyzers
    _registered_channel_cmds: dict[str, object] = {"register": RegisterChannel}
    _ = _registered_channel_cmds
