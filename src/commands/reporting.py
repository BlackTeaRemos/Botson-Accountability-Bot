"""Reporting-related slash commands (weekly reports and style settings)."""

from datetime import datetime
import discord
from typing import Any

from ..services.persistence import PersistenceService
from ..services.reporting import ReportingService
from ..services.channel_registration import ChannelRegistrationService
from ..core.config import AppConfig


def RegisterReportingCommands(
    bot: Any,
    storage: PersistenceService,
    reporting: ReportingService,
    channels: ChannelRegistrationService,
    config: AppConfig,
) -> None:
    """Register reporting-related slash commands on the bot.

    Args:
        bot: The Discord bot instance.
        storage: The persistence service instance.
        reporting: The reporting service instance.
        channels: The channel registration service instance.
        config: The application configuration.

    Returns:
        None

    Example:
        RegisterReportingCommands(bot, storage, reporting, channels, config)
    """
    # ----- Internal implementations to allow reuse between top-level and grouped commands -----
    async def _WeeklyReportImpl(interaction: discord.Interaction) -> None:
        try:
            guild_style = None
            if interaction.guild_id:
                guild_style = storage.get_guild_report_style(interaction.guild_id)
            channel_id = interaction.channel_id
            if channel_id is None:
                await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                return
            bad_dates = storage.detect_non_iso_dates(channel_id)
            purge_prefix = ""
            if bad_dates:
                deleted_count, deleted_list = storage.purge_non_iso_dates(channel_id)
                deleted_list_str = ', '.join(deleted_list[:10]) + (', ...' if len(deleted_list) > 10 else '')
                purge_prefix = f"Purged {deleted_count} malformed daily rows (dates: {deleted_list_str}).\n"
            buf, dates, warnings = reporting.generate_weekly_table_image(days=7, style=guild_style or "style1")
            if any('Dropped row' in w or 'Dropped' in w for w in warnings):
                deleted, deleted_dates = storage.purge_non_iso_dates(channel_id)
                buf, dates, warnings = reporting.generate_weekly_table_image(days=7, style=guild_style or "style1")
                if deleted_dates:
                    deleted_list_str = ', '.join(deleted_dates[:10]) + (', ...' if len(deleted_dates) > 10 else '')
                    purge_note = f"\nNote: purged {deleted} malformed daily rows (dates: {deleted_list_str}) before rendering."
                else:
                    purge_note = f"\nNote: purged {deleted} malformed daily rows before rendering."
            else:
                purge_note = ""
            if not dates:
                await interaction.response.send_message("No data for last 7 days yet.", ephemeral=True)
                return
            file = discord.File(buf, filename="weekly_report.png")
            warning_text = "" if not warnings else "\n" + "\n".join(f"Note: {w}" for w in warnings[:5]) + ("\n..." if len(warnings) > 5 else "")
            message_content = purge_prefix + "Weekly normalized scores (0-5 per day, scaled by daily max)." + purge_note + warning_text
            await interaction.response.send_message(
                content=message_content,
                file=file,
                ephemeral=False,
            )
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Error generating report: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Error generating report: {e}", ephemeral=True)
            except Exception:
                print(f"[weekly_report] Failed to send error response: {e}")
    pass

    async def _WeeklyEmbedImpl(interaction: discord.Interaction) -> None:
        try:
            channel_id = interaction.channel_id
            if channel_id is None:
                await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                return
            bad_dates = storage.detect_non_iso_dates(channel_id)
            purge_prefix = ""
            if bad_dates:
                deleted_count, deleted_list = storage.purge_non_iso_dates(channel_id)
                deleted_list_str = ', '.join(deleted_list[:10]) + (', ...' if len(deleted_list) > 10 else '')
                purge_prefix = f"Purged {deleted_count} malformed daily rows (dates: {deleted_list_str}).\n"
            dates, per_user, totals, warnings = reporting.get_weekly_structured(days=7)
            if any('Dropped row' in w or 'Dropped' in w for w in warnings):
                deleted, deleted_dates = storage.purge_non_iso_dates(channel_id)
                dates, per_user, totals, warnings = reporting.get_weekly_structured(days=7)
                if deleted_dates:
                    deleted_list_str = ', '.join(deleted_dates[:10]) + (', ...' if len(deleted_dates) > 10 else '')
                    purge_note = f"\nPurged {deleted} malformed daily rows (dates: {deleted_list_str}) before rendering."
                else:
                    purge_note = f"\nPurged {deleted} malformed daily rows before rendering."
            else:
                purge_note = ""
            if not dates:
                await interaction.response.send_message("No data for last 7 days yet.", ephemeral=True)
                return
            human_dates = [datetime.strptime(d, '%Y-%m-%d').strftime('%b %d') for d in dates]
            embed = discord.Embed(title="Weekly Habit Report", description=f"Last {len(dates)} days", color=0x5865F2)
            lines: list[str] = []
            for user_entry in per_user:
                uid = str(user_entry['user_id'])
                display = f"<@{uid}>" if uid.isdigit() else uid[:8]
                day_scores = [f"{user_entry.get(d,0):.1f}" for d in dates]
                total = user_entry['total']
                lines.append(f"{display} | {' '.join(day_scores)} | {total:.1f}")
            chunk: list[str] = []
            current_len = 0
            for line in lines:
                if current_len + len(line) + 1 > 950 and chunk:
                    embed.add_field(name="Players", value="\n".join(chunk), inline=False)
                    chunk = []
                    current_len = 0
                chunk.append(line)
                current_len += len(line) + 1
            if chunk:
                embed.add_field(name="Players", value="\n".join(chunk), inline=False)
            totals_line = ' '.join(f"{totals[d]:.1f}" for d in dates)
            embed.add_field(name="Dates", value=' '.join(human_dates), inline=False)
            embed.add_field(name="Totals", value=totals_line, inline=False)
            if warnings:
                warn_join = "\n".join(warnings[:5]) + ("\n..." if len(warnings) > 5 else "")
                embed.add_field(name="Data Notes", value=warn_join[:1000], inline=False)
                if any('Dropped row' in w or 'unparseable date' in w for w in warnings):
                    embed.add_field(name="Action Required", value=(
                        "Some rows were malformed and dropped. Run /debug_purge_bad_dates in this channel to remove them permanently from the database."), inline=False)
            if purge_prefix or purge_note:
                # Attach purge prefix and note to embed description if present
                embed.description = (purge_prefix or '') + (embed.description or '') + (purge_note or '')
            await interaction.response.send_message(embed=embed, ephemeral=False)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Embed report error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Embed report error: {e}", ephemeral=True)
    # No-op
    pass

    async def _SetReportStyleImpl(interaction: discord.Interaction, style: str) -> None:
        valid = {"style1","style2","style3","style4"}
        if style not in valid:
            await interaction.response.send_message(f"Invalid style. Choose one of: {', '.join(sorted(valid))}.", ephemeral=True)
            return
        if not interaction.guild_id:
            await interaction.response.send_message("This command must be used in a guild.", ephemeral=True)
            return
        storage.set_guild_report_style(interaction.guild_id, style)
        await interaction.response.send_message(f"Report style set to {style}.", ephemeral=True)
    # No-op
    pass

    async def _ClearWeekImpl(interaction: discord.Interaction) -> None:
        try:
            channel_id = interaction.channel_id
            if channel_id is None:
                await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                return
            if not storage.is_channel_registered(channel_id):
                await interaction.response.send_message("Channel not registered.", ephemeral=True)
                return
            deleted = storage.clear_current_week_scores(channel_id)
            await interaction.response.send_message(f"Cleared {deleted} daily score rows for current week.", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Clear failed: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Clear failed: {e}", ephemeral=True)
    # No-op
    pass

    async def _BackfillImpl(interaction: discord.Interaction) -> None:
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
            fetched = await channels.backfill_recent(channel, days=7)
            await interaction.followup.send(f"Backfill complete. Processed {fetched} messages.")
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Backfill failed: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Backfill failed: {e}", ephemeral=True)

    # ----- New grouped commands under /report -----
    from discord import app_commands

    report_group = app_commands.Group(name="report", description="Reporting commands")

    @report_group.command(name="weekly", description="Generate a weekly report image (normalized scores)")
    async def ReportWeekly(interaction: discord.Interaction):
        await _WeeklyReportImpl(interaction)

    @report_group.command(name="embed", description="Generate weekly report as an embed (no image)")
    async def ReportEmbed(interaction: discord.Interaction):
        await _WeeklyEmbedImpl(interaction)

    @report_group.command(name="clear_week", description="Clear current week's daily scores for this channel")
    async def ReportClearWeek(interaction: discord.Interaction):
        await _ClearWeekImpl(interaction)

    @report_group.command(name="backfill", description="Backfill last 7 days of messages for this channel")
    async def ReportBackfill(interaction: discord.Interaction):
        await _BackfillImpl(interaction)

    # Subgroup: /report style set
    style_group = app_commands.Group(name="style", description="Report style commands", parent=report_group)

    from discord.app_commands import Choice

    @style_group.command(name="set", description="Set weekly report style")
    @app_commands.describe(style="Report style theme")
    @app_commands.choices(
        style=[
            Choice(name="style1", value="style1"),
            Choice(name="style2", value="style2"),
            Choice(name="style3", value="style3"),
            Choice(name="style4", value="style4"),
        ]
    )
    async def ReportStyleSet(interaction: discord.Interaction, style: str):
        await _SetReportStyleImpl(interaction, style)

    # Finally, add the group (and its subgroup) to the bot tree
    bot.tree.add_command(report_group)

    # Keep explicit references to subcommand callables to appease static analyzers
    _registered_report_commands: dict[str, object] = {
        "weekly": ReportWeekly,
        "embed": ReportEmbed,
        "clear_week": ReportClearWeek,
        "backfill": ReportBackfill,
        "style_set": ReportStyleSet,
    }
    _ = _registered_report_commands
