# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from __future__ import annotations
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition
from ...services.persistence import PersistenceService
from ...services.reporting import schedulable_reports
from ...security import safe_send


class ScheduleCreateAnchored(CommandDefinition):
    group_name = None  # attaches to parent group
    group_description = ""

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        bot: Any = ctx.get("bot")
        storage = ctx.get("storage")

        async def _send_public(interaction: discord.Interaction, content: str) -> None:
            try:
                ch = getattr(interaction, "channel", None)
                allowed_types = {
                    getattr(discord.ChannelType, "text", None),
                    getattr(discord.ChannelType, "news", None),
                    getattr(discord.ChannelType, "public_thread", None),
                    getattr(discord.ChannelType, "private_thread", None),
                    getattr(discord.ChannelType, "news_thread", None),
                }
                if ch is not None and hasattr(ch, "send"):
                    ctype = getattr(ch, "type", None)
                    if ctype in allowed_types:
                        try:
                            await ch.send(content)  # type: ignore[attr-defined]
                            return
                        except Exception:
                            pass
                cid = getattr(interaction, "channel_id", None)
                if cid and hasattr(bot, "get_channel"):
                    target = bot.get_channel(cid)
                    if target is not None and hasattr(target, "send"):
                        ttype = getattr(target, "type", None)
                        if ttype not in allowed_types:
                            return
                        try:
                            await target.send(content)  # type: ignore[attr-defined]
                            return
                        except Exception:
                            pass
            except Exception:
                pass

        @group.command(name="create_anchored", description="Create a weekly anchored scheduled event (supports '@offset' e.g., w1@d2h10)")
        @app_commands.describe(
            report_type="What to run (pick from suggestions)",
            expression="Interval or interval@offset. Examples: d2h4, w1@d2h10, w2@h9m30"
        )
        async def create_anchored(interaction: discord.Interaction, report_type: str, expression: str):
            try:
                await interaction.response.defer(ephemeral=True, thinking=True)
            except Exception:
                pass
            cid = interaction.channel_id
            if cid is None:
                await safe_send(interaction, "Must be used in a channel.", ephemeral=True)
                return
            if not storage.is_channel_registered(cid):
                await safe_send(interaction, "Channel not registered.", ephemeral=True)
                return
            try:
                if report_type not in schedulable_reports:
                    await safe_send(interaction, "Invalid report type.", ephemeral=True)
                    return
                anchor_l = "week"
                # Validate/preview expression and compute next run for user feedback
                from ...services.schedule_expression import (
                    compute_next_run_from_week_expr,
                    compute_next_run_from_anchor,
                )
                expr = (expression or "").strip().lower()
                try:
                    if "@" in expr:
                        next_run, _ = compute_next_run_from_week_expr(expr)
                    else:
                        next_run, _ = compute_next_run_from_anchor(anchor_l, expr)
                except Exception as e:
                    help_text = (
                        "```\n"
                        f"Invalid expression: {e}\n"
                        "\n"
                        "Tokens:\n"
                        "  w = weeks, d = days, h = hours, m = minutes\n"
                        "\n"
                        "Examples:\n"
                        "  d2h4      -> every 2 days and 4 hours from week start\n"
                        "  w1@d2h10  -> every week at Wednesday 10:00\n"
                        "  w2@h9m30  -> every 2 weeks at Monday 09:30\n"
                        "```"
                    )
                    await safe_send(interaction, help_text, ephemeral=True)
                    return
                event_id = storage.add_event(
                    channel_discord_id=cid,
                    interval_minutes=0,
                    command=report_type,
                    schedule_anchor=anchor_l,
                    schedule_expr=expr,
                )
                await interaction.followup.send(
                    f"Anchored event {event_id} created: {report_type} every '{expr}' (weekly). Next run at {next_run.isoformat()}.",
                    ephemeral=True,
                )
                await _send_public(interaction, f"Scheduled event {event_id} created: {report_type} every '{expr}'. First run at {next_run.isoformat()}.")
            except Exception as e:
                await safe_send(interaction, f"Error creating anchored event: {e}", ephemeral=True)

        @create_anchored.autocomplete("report_type")
        async def report_type_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> list[app_commands.Choice[str]]:
            suggestions = [
                app_commands.Choice(name=rt, value=rt)
                for rt in schedulable_reports
                if current.lower() in rt.lower()
            ]
            return suggestions[:25]
