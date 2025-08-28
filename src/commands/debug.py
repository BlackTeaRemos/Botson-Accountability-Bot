"""Debug and developer helper slash commands."""

from typing import Any, Callable, Dict
import discord
from ..services.persistence import PersistenceService


def register_debug_commands(
    bot: Any,
    storage: PersistenceService,
    generate_random_user_recent: Callable[..., Dict[str, Any]],
) -> None:
    @bot.tree.command(name="debug_add_score", description="DEBUG: Add raw score delta to user for a date")
    async def debug_add_score(interaction: discord.Interaction, user_id: str, date: str, delta: float):
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
        _ = debug_add_score

    @bot.tree.command(name="debug_remove_score", description="DEBUG: Remove raw score delta from user for a date")
    async def debug_remove_score(interaction: discord.Interaction, user_id: str, date: str, delta: float):
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
        _ = debug_remove_score

    @bot.tree.command(name="debug_user_info", description="DEBUG: Show recent daily stats for a user")
    async def debug_user_info(interaction: discord.Interaction, user_id: str):
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
        _ = debug_user_info

    @bot.tree.command(name="debug_purge_bad_dates", description="DEBUG: Purge non-ISO date rows (drops malformed dates) for this channel")
    async def debug_purge_bad_dates(interaction: discord.Interaction):
        try:
            cid = interaction.channel_id
            if cid is None:
                await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                return
            if not storage.is_channel_registered(cid):
                await interaction.response.send_message("Channel not registered.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            deleted = storage.purge_non_iso_dates(cid)
            await interaction.followup.send(
                f"Purge complete. Deleted {deleted} daily rows (and related per-message scores).",
                ephemeral=True,
            )
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Purge failed: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Purge failed: {e}", ephemeral=True)
        _ = debug_purge_bad_dates

    @bot.tree.command(name="debug_generate_user", description="DEBUG: Generate clustered test user messages for this channel")
    async def debug_generate_user(
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
        _ = debug_generate_user
