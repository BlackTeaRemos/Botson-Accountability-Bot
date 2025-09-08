# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from typing import Any
from datetime import datetime
import discord
from discord import app_commands
from ..framework import CommandDefinition


class ReportWeekly(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage = ctx["storage"]
        reporting = ctx["reporting"]

        async def _send_embed_report(
            interaction: discord.Interaction,
            date_list: list[str],
            per_user_data: list[Any],
            warnings_list: list[str],
            purge_message_prefix: str,
            purge_note_message: str,
            user_display_names: dict[str, str],
            *,
            followup: bool = False,
        ) -> None:
            human_readable_dates = [datetime.strptime(d, "%Y-%m-%d").strftime("%a ") for d in date_list]
            all_time_totals = reporting.get_all_time_totals()
            embed_list: list[discord.Embed] = []
            for user_data in per_user_data:
                user_id_string = str(user_data["user_id"])
                resolved = reporting.resolve_display_name(user_id_string, user_display_names)
                if not resolved:
                    continue
                display_name = resolved
                if len(display_name) > 15:
                    display_name = display_name[:12] + "..."
                daily_lines: list[str] = []
                for i, date in enumerate(date_list):
                    day_name = human_readable_dates[i].strip()
                    score = user_data.get(date, 0)
                    daily_lines.append(f"{day_name} {score:.1f}")
                all_time_total = all_time_totals.get(user_id_string, 0)
                embed = discord.Embed(title=f"Weekly Report - {display_name}", color=0x5865F2)
                embed.add_field(name="Daily Scores", value="```\n" + "\n".join(daily_lines) + "\n```", inline=False)
                embed.add_field(name="Total", value=f"{user_data['total']:.1f}", inline=True)
                embed.add_field(name="All Time", value=f"{all_time_total:.1f}", inline=True)
                if len(embed_list) < 9:
                    embed_list.append(embed)
            summary_embed = discord.Embed(
                title="Weekly Summary",
                description=f"Top {min(len(per_user_data), 9)} players",
                color=0x57F287,
            )
            user_score_lines: list[str] = []
            for user_data in per_user_data:
                user_id_string = str(user_data["user_id"])
                resolved = reporting.resolve_display_name(user_id_string, user_display_names)
                if not resolved:
                    continue
                display_name = resolved
                if len(display_name) > 20:
                    display_name = display_name[:17] + "..."
                weekly_total = user_data["total"]
                if len(user_score_lines) < 9:
                    user_score_lines.append(f"{display_name:<20} {weekly_total:>5.1f}")
            summary_embed.add_field(name="Player Scores", value="```\n" + "\n".join(user_score_lines) + "\n```", inline=False)
            if warnings_list:
                warnings_joined = "\n".join(warnings_list[:5]) + ("\n..." if len(warnings_list) > 5 else "")
                summary_embed.add_field(name="Data Notes", value=warnings_joined[:1000], inline=False)
            if purge_message_prefix or purge_note_message:
                summary_embed.description = (purge_message_prefix or "") + (summary_embed.description or "") + (purge_note_message or "")
            embed_list.append(summary_embed)
            if followup:
                await interaction.followup.send(embeds=embed_list, ephemeral=False)
            else:
                await interaction.response.send_message(embeds=embed_list, ephemeral=False)

        @group.command(name="weekly", description="Generate a weekly report image (normalized scores)")
        async def _cmd(interaction: discord.Interaction):
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
                    deleted_dates_string = ", ".join(deleted_dates_list[:10]) + (", ..." if len(deleted_dates_list) > 10 else "")
                    purge_message_prefix = f"Purged {deleted_rows_count} malformed daily rows (dates: {deleted_dates_string}).\n"
                user_display_names: dict[str, str] = {}
                if interaction.guild:
                    try:
                        members = interaction.guild.members
                        user_display_names = {str(m.id): m.display_name for m in members}
                    except Exception:
                        pass
                date_list, per_user_data, _daily_totals, warnings_list = reporting.get_weekly_structured(days=7)
                if any("Dropped row" in w or "Dropped" in w for w in warnings_list):
                    deleted_rows, deleted_dates_list = storage.purge_non_iso_dates(channel_id)
                    date_list, per_user_data, _daily_totals, warnings_list = reporting.get_weekly_structured(days=7)
                    if deleted_dates_list:
                        deleted_dates_string = ", ".join(deleted_dates_list[:10]) + (", ..." if len(deleted_dates_list) > 10 else "")
                        purge_note_message = f"\nNote: purged {deleted_rows} malformed daily rows (dates: {deleted_dates_string}) before rendering."
                    else:
                        purge_note_message = f"\nNote: purged {deleted_rows} malformed daily rows before rendering."
                else:
                    purge_note_message = ""
                if not date_list:
                    await interaction.response.send_message("No data for last 7 days yet.", ephemeral=True)
                    return
                user_count = len(per_user_data)
                if user_count < 10:
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
                    await _send_embed_report(
                        interaction,
                        date_list,
                        per_user_data,
                        warnings_list,
                        purge_message_prefix,
                        purge_note_message,
                        user_display_names,
                    )
                    image_buffer, _dates, warnings = reporting.generate_weekly_table_image(
                        days=7, style=guild_style or "style1", user_names=user_display_names
                    )
                    file = discord.File(image_buffer, filename="weekly_report.png")
                    warning_message = "" if not warnings else "\n" + "\n".join(f"Note: {w}" for w in warnings[:5]) + ("\n..." if len(warnings) > 5 else "")
                    message_content = "Weekly normalized scores." + warning_message
                    await interaction.followup.send(content=message_content, file=file, ephemeral=False)
            except Exception as e:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(f"Error generating report: {e}", ephemeral=True)
                    else:
                        await interaction.followup.send(f"Error generating report: {e}", ephemeral=True)
                except Exception:
                    print(f"[weekly_report] Failed to send error response: {e}")
