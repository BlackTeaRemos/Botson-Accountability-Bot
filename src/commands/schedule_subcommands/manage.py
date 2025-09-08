# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from __future__ import annotations
from typing import Any
import re
import discord
from discord import app_commands
from ..framework import CommandDefinition
from ...services.persistence import PersistenceService
from ...services.reporting import schedulable_reports
from ...security import safe_send, has_admin
from ...security.interaction_chain import Chain


class ScheduleManage(CommandDefinition):
    group_name = None
    group_description = ""

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        bot: Any = ctx.get("bot")
        storage = ctx.get("storage")

        class ExpressionPromptView(discord.ui.View):
            def __init__(self, storage: PersistenceService, report_type: str, bot: Any, timeout: float | None = 180.0):
                super().__init__(timeout=timeout)
                self.storage = storage
                self.report_type = report_type
                self.bot = bot

            @discord.ui.button(label="Enter interval/@offset", style=discord.ButtonStyle.primary, custom_id="open_expression_modal_v1")
            async def open_expression(self, interaction: discord.Interaction, button: Any):
                try:
                    await interaction.response.send_modal(ExpressionModal(self.storage, self.report_type, self.bot))
                except Exception as e:
                    try:
                        await interaction.followup.send(f"Error: {e}", ephemeral=True)
                    except Exception:
                        pass

        class ExpressionModal(discord.ui.Modal, title="Enter Weekly Expression"):
            def __init__(self, storage: PersistenceService, report_type: str, bot: Any):
                super().__init__()
                self.storage = storage
                self.report_type = report_type
                self.bot = bot
                self.expression: Any = discord.ui.TextInput(
                    label="Expression: interval or interval@offset",
                    placeholder="Examples: d2h4, w1@d2h10, w2@h9m30",
                    required=True,
                    max_length=64,
                )
                self.add_item(self.expression)

            async def on_submit(self, interaction: discord.Interaction):
                expr = str(self.expression.value or "").strip().lower()
                if not expr:
                    await interaction.response.send_message("Expression cannot be empty.", ephemeral=True)
                    return
                # Validate using schedule expression helpers; weekly anchor is assumed here
                try:
                    from ...services.schedule_expression import (
                        compute_next_run_from_anchor,
                        compute_next_run_from_week_expr,
                    )
                    if "@" in expr:
                        compute_next_run_from_week_expr(expr)
                    else:
                        compute_next_run_from_anchor("week", expr)
                except Exception as e:
                    await interaction.response.send_message(
                        f"Invalid expression: {e}. Use tokens w/d/h/m. Examples: 'd2h4', 'w1@d2h10', 'w2@h9m30'.",
                        ephemeral=True,
                    )
                    return
                view = MentionTypeSelectView(self.storage, self.report_type, expr, self.bot)
                await interaction.response.send_message("Choose mention type:", view=view, ephemeral=True)

        class MentionTypeSelectView(discord.ui.View):
            def __init__(self, storage: PersistenceService, report_type: str, expr: str, bot: Any, timeout: float | None = 180.0):
                super().__init__(timeout=timeout)
                self.storage = storage
                self.report_type = report_type
                self.expr = expr
                self.bot = bot
                options = [
                    discord.SelectOption(label="No mention", value="none"),
                    discord.SelectOption(label="User", value="user"),
                    discord.SelectOption(label="@here (admin)", value="here"),
                    discord.SelectOption(label="@everyone (admin)", value="everyone"),
                ]
                self.select: Any = discord.ui.Select(
                    placeholder="Mention type",
                    min_values=1,
                    max_values=1,
                    options=options,
                    custom_id="mention_type_select_v1",
                )
                self.add_item(self.select)

                async def _on_select(interaction: discord.Interaction) -> None:
                    try:
                        mt = self.select.values[0]
                        if mt in ("here", "everyone"):
                            try:
                                if not has_admin(interaction):
                                    await interaction.response.send_message("Only admins can use @here or @everyone.", ephemeral=True)
                                    return
                            except Exception:
                                await interaction.response.send_message("Permission check failed.", ephemeral=True)
                                return
                        if mt == "user":
                            await interaction.response.send_modal(UserIdModal(self.storage, self.report_type, self.expr))
                            return
                        target_user_id: str | None = None

                        if self.report_type == "reminder":
                            await interaction.response.send_modal(ReminderTextModal(self.storage, self.expr, mention_type=mt, target_user_id=target_user_id))
                            return

                        cid = interaction.channel_id
                        if cid is None:
                            await interaction.response.send_message("Must be used in a channel.", ephemeral=True)
                            return
                        if self.report_type not in schedulable_reports:
                            await interaction.response.send_message("Invalid report type.", ephemeral=True)
                            return
                        event_id = self.storage.add_event(
                            channel_discord_id=cid,
                            interval_minutes=0,
                            command=self.report_type,
                            schedule_anchor="week",
                            schedule_expr=self.expr,
                            target_user_id=target_user_id,
                            mention_type=mt,
                        )
                        note = (
                            "No mention." if mt == 'none' else (
                                "Will ping @here." if mt == 'here' else (
                                    "Will ping @everyone." if mt == 'everyone' else f"Will ping <@{target_user_id}>."
                                )
                            )
                        )
                        try:
                            await interaction.response.send_message(
                                f"Created weekly event {event_id}: {self.report_type} every '{self.expr}'. {note}",
                                ephemeral=True,
                            )
                        except Exception:
                            await interaction.followup.send(
                                f"Created weekly event {event_id}: {self.report_type} every '{self.expr}'. {note}",
                                ephemeral=True,
                            )

                    except Exception as e:
                        try:
                            await interaction.response.send_message(f"Error: {e}", ephemeral=True)
                        except Exception:
                            try:
                                await interaction.followup.send(f"Error: {e}", ephemeral=True)
                            except Exception:
                                pass

                self.select.callback = _on_select  # type: ignore[assignment]

        class UserIdModal(discord.ui.Modal, title="Target User (optional)"):
            def __init__(self, storage: PersistenceService, report_type: str, expr: str):
                super().__init__()
                self.storage = storage
                self.report_type = report_type
                self.expr = expr
                self.user_id_input: Any = discord.ui.TextInput(
                    label="User ID (or 'me')",
                    placeholder="me",
                    required=False,
                    max_length=32,
                )
                self.add_item(self.user_id_input)

            async def on_submit(self, interaction: discord.Interaction):
                try:
                    raw = str(self.user_id_input.value or "me").strip().lower()
                    if raw in ("", "me"):
                        target_user_id = str(interaction.user.id)
                    else:
                        if not raw.isdigit():
                            await interaction.response.send_message("User id must be numeric.", ephemeral=True)
                            return
                        if str(interaction.user.id) != raw:
                            try:
                                if not has_admin(interaction):
                                    await interaction.response.send_message("Only admins can create schedules for others.", ephemeral=True)
                                    return
                            except Exception:
                                await interaction.response.send_message("Permission check failed.", ephemeral=True)
                                return
                        target_user_id = raw

                    if self.report_type == "reminder":
                        view = discord.ui.View(timeout=120)
                        open_btn: Any = discord.ui.Button(label="Enter reminder text", style=discord.ButtonStyle.primary, custom_id="open_reminder_text_v1")

                        async def _open_next(i: discord.Interaction):
                            try:
                                await i.response.send_modal(ReminderTextModal(self.storage, self.expr, mention_type="user", target_user_id=target_user_id))
                            except Exception as e:
                                try:
                                    await i.followup.send(f"Error: {e}", ephemeral=True)
                                except Exception:
                                    pass

                        open_btn.callback = _open_next  # type: ignore[method-assign]
                        view.add_item(open_btn)  # type: ignore[arg-type]
                        await interaction.response.send_message("Click the button to enter the reminder text:", view=view, ephemeral=True)
                        return

                    cid = interaction.channel_id
                    if cid is None:
                        await interaction.response.send_message("Must be used in a channel.", ephemeral=True)
                        return
                    if self.report_type not in schedulable_reports:
                        await interaction.response.send_message("Invalid report type.", ephemeral=True)
                        return
                    event_id = self.storage.add_event(
                        channel_discord_id=cid,
                        interval_minutes=0,
                        command=self.report_type,
                        schedule_anchor="week",
                        schedule_expr=self.expr,
                        target_user_id=target_user_id,
                        mention_type="user",
                    )
                    await interaction.response.send_message(
                        f"Created weekly event {event_id}: {self.report_type} every '{self.expr}'. Will ping <@{target_user_id}>.",
                        ephemeral=True,
                    )
                except Exception as e:
                    await interaction.response.send_message(f"Error: {e}", ephemeral=True)

        class ReminderTextModal(discord.ui.Modal, title="Reminder Message"):
            def __init__(self, storage: PersistenceService, expr: str, *, mention_type: str, target_user_id: str | None):
                super().__init__()
                self.storage = storage
                self.expr = expr
                self.mention_type = mention_type
                self.target_user_id = target_user_id
                self.text_input: Any = discord.ui.TextInput(
                    label="Message to post",
                    placeholder="Don't forget to hydrate!",
                    required=True,
                    max_length=100,
                    style=discord.TextStyle.paragraph,
                )
                self.add_item(self.text_input)

            async def on_submit(self, interaction: discord.Interaction):
                msg = str(self.text_input.value or "").strip()
                if not msg:
                    await interaction.response.send_message("Message cannot be empty.", ephemeral=True)
                    return
                # Sanitize mentions anywhere in the text and enforce limit at creation time
                # Remove user mentions like <@123> or <@!123>
                msg = re.sub(r"<@!?\d+>", "", msg)
                # Remove broadcast mentions
                msg = re.sub(r"@everyone|@here", "", msg, flags=re.IGNORECASE)
                msg = msg.strip()
                if not msg:
                    await interaction.response.send_message("Message cannot be only mentions.", ephemeral=True)
                    return
                if len(msg) > 100:
                    await interaction.response.send_message("Reminder text must be 100 characters or fewer.", ephemeral=True)
                    return
                cid = interaction.channel_id
                if cid is None:
                    await interaction.response.send_message("Must be used in a channel.", ephemeral=True)
                    return
                command_key = f"reminder:{msg}"
                event_id = self.storage.add_event(
                    channel_discord_id=cid,
                    interval_minutes=0,
                    command=command_key,
                    schedule_anchor="week",
                    schedule_expr=self.expr,
                    target_user_id=self.target_user_id,
                    mention_type=self.mention_type,
                )
                await interaction.response.send_message(
                    f"Created weekly reminder {event_id} every '{self.expr}'.",
                    ephemeral=True,
                )

        class ScheduleManagerView(discord.ui.View):
            def __init__(self, storage: PersistenceService, items: list[dict[str, Any]], timeout: float | None = 120.0):
                super().__init__(timeout=timeout)
                self.storage = storage
                self.items_cache = items
                def _clamp(s: str, max_len: int = 100) -> str:
                    if len(s) <= max_len:
                        return s
                    return s[: max_len - 3] + "..."

                options: list[discord.SelectOption] = []
                for ev in items:
                    raw_cmd = str(ev.get('command', ''))
                    if ':' in raw_cmd:
                        cmd_base, cmd_detail = raw_cmd.split(':', 1)
                    else:
                        cmd_base, cmd_detail = raw_cmd, None

                    if ev.get('schedule_anchor') and ev.get('schedule_expr'):
                        label = f"ID {ev['id']} | {cmd_base} | {ev['schedule_anchor']}:{ev['schedule_expr']}"
                    else:
                        label = f"ID {ev['id']} | {cmd_base} | {ev.get('interval_minutes', 0)}m"
                    label = _clamp(label, 100)

                    description: str | None = None
                    if cmd_base == 'reminder' and cmd_detail:
                        preview = cmd_detail.strip()
                        if preview:
                            description = _clamp(preview, 100)

                    options.append(discord.SelectOption(label=label, value=str(ev['id']), description=description))

                disabled = False
                if len(options) == 0:
                    disabled = True
                    options = [discord.SelectOption(label="No events found", value="none", description="Use Create buttons to add", default=True)]
                    max_vals = 1
                else:
                    max_vals = min(25, len(options))

                self.select: Any = discord.ui.Select(
                    placeholder="Select events to manage",
                    min_values=0,
                    max_values=max_vals,
                    options=options,
                    disabled=disabled,
                )
                self.add_item(self.select)

                async def _on_select(interaction: discord.Interaction) -> None:
                    try:
                        await interaction.response.defer(ephemeral=True)
                    except Exception:
                        pass

                self.select.callback = _on_select  # type: ignore[assignment]

            @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary)
            async def refresh(self, interaction: discord.Interaction, button: Any):
                cid = interaction.channel_id
                if cid is None:
                    await interaction.response.send_message("Must be used in a channel.", ephemeral=True)
                    return
                events = self.storage.list_events(channel_discord_id=cid)
                await interaction.response.edit_message(view=ScheduleManagerView(self.storage, events))

            @discord.ui.button(label="Remove Selected", style=discord.ButtonStyle.danger)
            async def remove_selected(self, interaction: discord.Interaction, button: Any):
                try:
                    if getattr(self.select, 'disabled', False):
                        await interaction.response.send_message("Nothing to remove.", ephemeral=True)
                        return
                    ids = []
                    for v in self.select.values:
                        if v == "none":
                            continue
                        try:
                            ids.append(int(v))
                        except Exception:
                            continue
                    removed = 0
                    for eid in ids:
                        if self.storage.remove_event(eid):
                            removed += 1
                    await interaction.response.send_message(f"Removed {removed} events.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"Error removing: {e}", ephemeral=True)

            @discord.ui.button(label="Create Anchored", style=discord.ButtonStyle.success, custom_id="schedule_create_anchored_v2")
            async def create_anchored(self, interaction: discord.Interaction, button: Any):
                try:
                    async def _on_pick(i: discord.Interaction, value: Any) -> None:
                        chosen = str(value)
                        explanation = (
                            "```\n"
                            "Enter interval\n"
                            "\n"
                            "  Syntax:\n"
                            "    interval@offset\n"
                            "\n"
                            "  Tokens:\n"
                            "    w = weeks, d = days, h = hours, m = minutes\n"
                            "\n"
                            "  Examples:\n"
                            "    d2h4       -> every 2 days and 4 hours from week start\n"
                            "    w1@d2h10   -> every week at Wednesday 10:00\n"
                            "    w2@h9m30   -> every 2 weeks at Monday 09:30\n"
                            "\n"
                            "Type your expression below and press Submit.\n"
                            "```"
                        )
                        view2 = ExpressionPromptView(self.storage, chosen, bot)
                        try:
                            if not i.response.is_done():
                                await i.response.send_message(explanation, view=view2, ephemeral=True)
                            else:
                                await i.followup.send(explanation, view=view2, ephemeral=True)
                        except Exception:
                            await safe_send(i, "Could not present the expression prompt.", ephemeral=True)

                    registry_keys = list(dict.fromkeys(list(schedulable_reports.keys())))
                    registry_keys = [k for k in registry_keys if k != "reminder"]
                    report_options = ["reminder"] + registry_keys
                    await Chain("Select a report type to schedule:") \
                        .with_select(report_options, placeholder="Pick a report type or 'reminder'") \
                        .on_invoke(_on_pick) \
                        .send(interaction)
                except Exception as e:
                    await safe_send(interaction, f"Failed to open creation flow: {e}", ephemeral=True)

        @group.command(name="manage", description="Open schedule manager UI")
        async def manage_schedule(interaction: discord.Interaction):
            cid = interaction.channel_id
            if cid is None:
                await interaction.response.send_message("Must be used in a channel.", ephemeral=True)
                return
            items = storage.list_events(channel_discord_id=cid)
            view = ScheduleManagerView(storage, items)
            heading = "Schedule Manager" if items else "Schedule Manager - no events yet"
            await interaction.response.send_message(heading, view=view, ephemeral=True)
