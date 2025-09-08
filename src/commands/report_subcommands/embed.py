# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from typing import Any
from datetime import datetime
import discord
from discord import app_commands
from ..framework import CommandDefinition


class ReportEmbed(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage = ctx["storage"]
        reporting = ctx["reporting"]

        @group.command(name="embed", description="Generate weekly report as an embed (no image)")
        async def _cmd(interaction: discord.Interaction):
            try:
                # Defer immediately to acknowledge the interaction and avoid timeouts
                await interaction.response.defer(ephemeral=False, thinking=True)
                channel_id = interaction.channel_id
                if channel_id is None:
                    await interaction.followup.send("This command must be used in a channel.", ephemeral=True)
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
                        purge_note_message = f"\nPurged {deleted_rows} malformed daily rows (dates: {deleted_dates_string}) before rendering."
                    else:
                        purge_note_message = f"\nPurged {deleted_rows} malformed daily rows before rendering."
                else:
                    purge_note_message = ""
                if not date_list:
                    await interaction.followup.send("No data for last 7 days yet.", ephemeral=True)
                    return
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
                summary_embed = discord.Embed(title="Weekly Summary", description=f"Top {min(len(per_user_data), 9)} players", color=0x57F287)
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
                await interaction.followup.send(embeds=embed_list, ephemeral=False)
            except Exception as e:
                await interaction.followup.send(f"Embed report error: {e}", ephemeral=True)
