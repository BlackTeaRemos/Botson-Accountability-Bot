"""Debug and developer helper slash commands."""

from typing import Any, Callable, Dict
import discord
from discord import app_commands
from ..services.persistence import PersistenceService


def RegisterDebugCommands(
    bot: Any,
    storage: PersistenceService,
    generate_random_user_recent: Callable[..., Dict[str, Any]],
) -> None:
    """Register debug and developer utility commands on the bot.

    Args:
        bot: The Discord bot instance.
        storage: The persistence service instance.
        generate_random_user_recent: Function to generate test user data.

    Returns:
        None

    Example:
        RegisterDebugCommands(bot, storage, generate_func)
    """
    debug_group = app_commands.Group(name="debug", description="Developer utilities")

    @debug_group.command(name="add_score", description="Add raw score delta to user for a date")
    async def DebugAddScore(interaction: discord.Interaction, user_id: str, date: str, delta: float):
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

    @debug_group.command(name="remove_score", description="Remove raw score delta from user for a date")
    async def DebugRemoveScore(interaction: discord.Interaction, user_id: str, date: str, delta: float):
        try:
            cid = interaction.channel_id
            if cid is None:
                await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                return
            if not storage.is_channel_registered(cid):
                await interaction.response.send_message("Channel not registered.", ephemeral=True)
                return
            storage.debug_remove_score(user_id=user_id, date=date, channel_discord_id=cid, delta=delta)
            await interaction.response.send_message(f"Removed {delta} raw from {user_id} on {date} (floor 0).", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @debug_group.command(name="user_info", description="Show recent daily stats for a user")
    async def DebugUserInfo(interaction: discord.Interaction, user_id: str):
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
                f"{d['date']}: raw={d['raw_score_sum']:.2f} msgs={d['messages_count']}"
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

    @debug_group.command(name="purge_bad_dates", description="Purge non-ISO date rows for this channel")
    async def DebugPurgeBadDates(interaction: discord.Interaction):
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

    @debug_group.command(name="generate_user", description="Generate clustered test user messages for this channel")
    async def DebugGenerateUser(
        interaction: discord.Interaction,
        user_id: str | None = None,
        messages: int = 5,
        dry_run: bool = True,
    ):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            cid = interaction.channel_id
            if cid is None:
                await interaction.followup.send("This command must be used in a channel.", ephemeral=True)
                return
            messages = max(1, min(200, int(messages)))
            result = generate_random_user_recent(
                channel_discord_id=cid,
                user_id=user_id,
                messages=messages,
                dry_run=dry_run,
            )
            written = result.get("written", False)
            sample_dates = sorted({m["extracted_date"] for m in result["messages"]})
            body = (
                f"Generated {len(result['messages'])} messages for user {result['user_id']}.\n"
                f"Dates: {', '.join(sample_dates[:10])}{'...' if len(sample_dates) > 10 else ''}\n"
                f"Written to DB: {written} (dry_run={dry_run})"
            )
            await interaction.followup.send(body, ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error generating user: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error generating user: {e}", ephemeral=True)

    # Register group on bot tree
    bot.tree.add_command(debug_group)

    # References for analyzers
    _registered_debug_commands: dict[str, object] = {
        "add_score": DebugAddScore,
        "remove_score": DebugRemoveScore,
        "user_info": DebugUserInfo,
        "purge_bad_dates": DebugPurgeBadDates,
        "generate_user": DebugGenerateUser,
    }
    _ = _registered_debug_commands
