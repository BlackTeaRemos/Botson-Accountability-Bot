"""Reporting-related slash commands (weekly reports and style settings).
"""

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
    async def _send_embed_report(interaction: discord.Interaction, date_list: list[str], per_user_data: list[Any], 
                               warnings_list: list[str], purge_message_prefix: str, purge_note_message: str, 
                               user_display_names: dict[str, str], followup: bool = False) -> None:
        """Helper function to send embed report, either as initial response or followup."""
        
        # Prepare human-readable dates
        human_readable_dates = [datetime.strptime(d, '%Y-%m-%d').strftime('%a ') for d in date_list]

        # Get all-time totals
        all_time_totals = reporting.get_all_time_totals()

        # Build individual embeds for top users; resolve names with fallback and skip unresolved
        embed_list: list[discord.Embed] = []
        for user_data in per_user_data:
            user_id_string = str(user_data['user_id'])
            resolved = reporting.resolve_display_name(user_id_string, user_display_names)
            if not resolved:
                continue
            display_name = resolved
            if len(display_name) > 15:
                display_name = display_name[:12] + '...'
            
            # Format daily scores
            daily_lines: list[str] = []
            for i, date in enumerate(date_list):
                day_name = human_readable_dates[i].strip()
                score = user_data.get(date, 0)
                daily_lines.append(f"{day_name} {score:.1f}")
            
            # Get all-time total
            all_time_total = all_time_totals.get(user_id_string, 0)
            
            # Create embed with proper field formatting
            embed = discord.Embed(
                title=f"Weekly Report - {display_name}", 
                color=0x5865F2
            )
            
            # Add daily scores as a field
            embed.add_field(
                name="Daily Scores", 
                value="```\n" + "\n".join(daily_lines) + "\n```", 
                inline=False
            )
            
            # Add totals as separate fields
            embed.add_field(name="Total", value=f"{user_data['total']:.1f}", inline=True)
            embed.add_field(name="All Time", value=f"{all_time_total:.1f}", inline=True)
            
            if len(embed_list) < 9:
                embed_list.append(embed)

        # Summary embed with totals and warnings
        summary_embed = discord.Embed(title="Weekly Summary", description=f"Top {min(len(per_user_data), 9)} players", color=0x57F287)
        
        # Create user scores list for the summary
        user_score_lines: list[str] = []
        for user_data in per_user_data:
            user_id_string = str(user_data['user_id'])
            resolved = reporting.resolve_display_name(user_id_string, user_display_names)
            if not resolved:
                continue
            display_name = resolved
            if len(display_name) > 20:  # Shorter limit for summary
                display_name = display_name[:17] + '...'
            weekly_total = user_data['total']
            if len(user_score_lines) < 9:
                user_score_lines.append(f"{display_name:<20} {weekly_total:>5.1f}")
        
        # Add user scores as a formatted field
        summary_embed.add_field(
            name="Player Scores", 
            value="```\n" + "\n".join(user_score_lines) + "\n```", 
            inline=False
        )
        
        if warnings_list:
            warnings_joined = "\n".join(warnings_list[:5]) + ("\n..." if len(warnings_list) > 5 else "")
            summary_embed.add_field(name="Data Notes", value=warnings_joined[:1000], inline=False)
        if purge_message_prefix or purge_note_message:
            summary_embed.description = (
                (purge_message_prefix or '') +
                (summary_embed.description or '') +
                (purge_note_message or '')
            )
        embed_list.append(summary_embed)

        if followup:
            await interaction.followup.send(embeds=embed_list, ephemeral=False)
        else:
            await interaction.response.send_message(embeds=embed_list, ephemeral=False)

    async def _weekly_report_implementation(interaction: discord.Interaction) -> None:
        try:

            guild_style = None
            if interaction.guild_id:
                guild_style = storage.get_guild_report_style(interaction.guild_id)

            channel_id = interaction.channel_id
            if channel_id is None:
                await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                return

            malformed_dates = storage.detect_non_iso_dates(channel_id)
            purge_message_prefix = ""
            if malformed_dates:
                deleted_rows_count, deleted_dates_list = storage.purge_non_iso_dates(channel_id)
                deleted_dates_string = ', '.join(deleted_dates_list[:10]) + (', ...' if len(deleted_dates_list) > 10 else '')
                purge_message_prefix = (
                    f"Purged {deleted_rows_count} malformed daily rows "
                    f"(dates: {deleted_dates_string}).\n"
                )

            # Fetch user names for display
            user_display_names = {}
            if interaction.guild:
                try:
                    # Get all members to build name map
                    members = interaction.guild.members
                    user_display_names = {str(member.id): member.display_name for member in members}
                except Exception:
                    pass  # If fetching fails, fall back to IDs

            # Get structured data to check user count
            date_list, per_user_data, _daily_totals, warnings_list = reporting.get_weekly_structured(days=7)
            if any('Dropped row' in w or 'Dropped' in w for w in warnings_list):
                deleted_rows, deleted_dates_list = storage.purge_non_iso_dates(channel_id)
                date_list, per_user_data, _daily_totals, warnings_list = reporting.get_weekly_structured(days=7)
                if deleted_dates_list:
                    deleted_dates_string = ', '.join(deleted_dates_list[:10]) + (', ...' if len(deleted_dates_list) > 10 else '')
                    purge_note_message = f"\nNote: purged {deleted_rows} malformed daily rows (dates: {deleted_dates_string}) before rendering."
                else:
                    purge_note_message = f"\nNote: purged {deleted_rows} malformed daily rows before rendering."
            else:
                purge_note_message = ""

            if not date_list:
                await interaction.response.send_message("No data for last 7 days yet.", ephemeral=True)
                return

            # Check user count to decide format
            user_count = len(per_user_data)

            if user_count < 10:
                # Use embed format for fewer users
                await _send_embed_report(
                    interaction,
                    date_list,
                    per_user_data,
                    warnings_list,
                    purge_message_prefix,
                    purge_note_message,
                    user_display_names,
                )
            else:
                # For 10+ users: send embed first, then image so embed appears on top
                await _send_embed_report(
                    interaction,
                    date_list,
                    per_user_data,
                    warnings_list,
                    purge_message_prefix,
                    purge_note_message,
                    user_display_names,
                )

                # Generate image after initial response
                image_buffer, _dates, warnings = reporting.generate_weekly_table_image(
                    days=7, style=guild_style or "style1", user_names=user_display_names
                )

                file = discord.File(image_buffer, filename="weekly_report.png")
                warning_message = (
                    "" if not warnings
                    else "\n" + "\n".join(f"Note: {w}" for w in warnings[:5]) + ("\n..." if len(warnings) > 5 else "")
                )
                message_content = (
                    # Purge notes are already included in the embed; keep image caption concise
                    "Weekly normalized scores (0-5 per day, scaled by daily max)." + warning_message
                )

                # Then send image as a follow-up
                await interaction.followup.send(
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

    async def _weekly_embed_implementation(interaction: discord.Interaction) -> None:
        try:

            channel_id = interaction.channel_id
            if channel_id is None:
                await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                return

            malformed_dates = storage.detect_non_iso_dates(channel_id)
            purge_message_prefix = ""
            if malformed_dates:
                deleted_rows_count, deleted_dates_list = storage.purge_non_iso_dates(channel_id)
                deleted_dates_string = ', '.join(deleted_dates_list[:10]) + (', ...' if len(deleted_dates_list) > 10 else '')
                purge_message_prefix = (
                    f"Purged {deleted_rows_count} malformed daily rows "
                    f"(dates: {deleted_dates_string}).\n"
                )

            # Fetch user names for display
            user_display_names = {}
            if interaction.guild:
                try:
                    # Get all members to build name map
                    members = interaction.guild.members
                    user_display_names = {str(member.id): member.display_name for member in members}
                except Exception:
                    pass  # If fetching fails, fall back to IDs

            date_list, per_user_data, _daily_totals, warnings_list = reporting.get_weekly_structured(days=7)
            if any('Dropped row' in w or 'Dropped' in w for w in warnings_list):
                deleted_rows, deleted_dates_list = storage.purge_non_iso_dates(channel_id)
                date_list, per_user_data, _daily_totals, warnings_list = reporting.get_weekly_structured(days=7)
                if deleted_dates_list:
                    deleted_dates_string = ', '.join(deleted_dates_list[:10]) + (', ...' if len(deleted_dates_list) > 10 else '')
                    purge_note_message = f"\nPurged {deleted_rows} malformed daily rows (dates: {deleted_dates_string}) before rendering."
                else:
                    purge_note_message = f"\nPurged {deleted_rows} malformed daily rows before rendering."
            else:
                purge_note_message = ""

            if not date_list:
                await interaction.response.send_message("No data for last 7 days yet.", ephemeral=True)
                return

            # Prepare human-readable dates
            human_readable_dates = [datetime.strptime(d, '%Y-%m-%d').strftime('%a ') for d in date_list]

            # Get all-time totals
            all_time_totals = reporting.get_all_time_totals()

            # Build individual embeds for top users; resolve names and skip unresolved
            embed_list: list[discord.Embed] = []
            for user_data in per_user_data:
                user_id_string = str(user_data['user_id'])
                resolved = reporting.resolve_display_name(user_id_string, user_display_names)
                if not resolved:
                    continue
                display_name = resolved
                if len(display_name) > 15:
                    display_name = display_name[:12] + '...'
                
                # Format daily scores
                daily_lines: list[str] = []
                for i, date in enumerate(date_list):
                    day_name = human_readable_dates[i].strip()
                    score = user_data.get(date, 0)
                    daily_lines.append(f"{day_name} {score:.1f}")
                
                # Get all-time total
                all_time_total = all_time_totals.get(user_id_string, 0)
                
                # Create embed with proper field formatting
                embed = discord.Embed(
                    title=f"Weekly Report - {display_name}", 
                    color=0x5865F2
                )
                
                # Add daily scores as a field
                embed.add_field(
                    name="Daily Scores", 
                    value="```\n" + "\n".join(daily_lines) + "\n```", 
                    inline=False
                )
                
                # Add totals as separate fields
                embed.add_field(name="Total", value=f"{user_data['total']:.1f}", inline=True)
                embed.add_field(name="All Time", value=f"{all_time_total:.1f}", inline=True)
                
                if len(embed_list) < 9:
                    embed_list.append(embed)

            # Summary embed with totals and warnings
            summary_embed = discord.Embed(title="Weekly Summary", description=f"Top {min(len(per_user_data), 9)} players", color=0x57F287)
            
            # Create user scores list for the summary
            user_score_lines: list[str] = []
            for user_data in per_user_data:
                user_id_string = str(user_data['user_id'])
                resolved = reporting.resolve_display_name(user_id_string, user_display_names)
                if not resolved:
                    continue
                display_name = resolved
                if len(display_name) > 20:  # Shorter limit for summary
                    display_name = display_name[:17] + '...'
                weekly_total = user_data['total']
                if len(user_score_lines) < 9:
                    user_score_lines.append(f"{display_name:<20} {weekly_total:>5.1f}")
            
            # Add user scores as a formatted field
            summary_embed.add_field(
                name="Player Scores", 
                value="```\n" + "\n".join(user_score_lines) + "\n```", 
                inline=False
            )
            
            if warnings_list:
                warnings_joined = "\n".join(warnings_list[:5]) + ("\n..." if len(warnings_list) > 5 else "")
                summary_embed.add_field(name="Data Notes", value=warnings_joined[:1000], inline=False)
            if purge_message_prefix or purge_note_message:
                summary_embed.description = (
                    (purge_message_prefix or '') +
                    (summary_embed.description or '') +
                    (purge_note_message or '')
                )
            embed_list.append(summary_embed)

            await interaction.response.send_message(embeds=embed_list, ephemeral=False)

        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Embed report error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Embed report error: {e}", ephemeral=True)

    async def _set_report_style_implementation(interaction: discord.Interaction, style: str) -> None:

        valid_styles = {"style1", "style2", "style3", "style4"}
        if style not in valid_styles:
            await interaction.response.send_message(f"Invalid style. Choose one of: {', '.join(sorted(valid_styles))}.", ephemeral=True)
            return

        if not interaction.guild_id:
            await interaction.response.send_message("This command must be used in a guild.", ephemeral=True)
            return

        storage.set_guild_report_style(interaction.guild_id, style)
        await interaction.response.send_message(f"Report style set to {style}.", ephemeral=True)

    async def _clear_week_implementation(interaction: discord.Interaction) -> None:
        try:

            channel_id = interaction.channel_id
            if channel_id is None:
                await interaction.response.send_message("This command must be used in a channel.", ephemeral=True)
                return

            if not storage.is_channel_registered(channel_id):
                await interaction.response.send_message("Channel not registered.", ephemeral=True)
                return

            deleted_rows = storage.clear_current_week_scores(channel_id)
            await interaction.response.send_message(f"Cleared {deleted_rows} daily score rows for current week.", ephemeral=True)

        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Clear failed: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Clear failed: {e}", ephemeral=True)

    async def _backfill_implementation(interaction: discord.Interaction) -> None:
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

            messages_fetched = await channels.backfill_recent(channel, days=7)
            await interaction.followup.send(f"Backfill complete. Processed {messages_fetched} messages.")

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
        await _weekly_report_implementation(interaction)

    @report_group.command(name="embed", description="Generate weekly report as an embed (no image)")
    async def ReportEmbed(interaction: discord.Interaction):
        await _weekly_embed_implementation(interaction)

    @report_group.command(name="clear_week", description="Clear current week's daily scores for this channel")
    async def ReportClearWeek(interaction: discord.Interaction):
        await _clear_week_implementation(interaction)

    @report_group.command(name="backfill", description="Backfill last 7 days of messages for this channel")
    async def ReportBackfill(interaction: discord.Interaction):
        await _backfill_implementation(interaction)

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
        await _set_report_style_implementation(interaction, style)

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
