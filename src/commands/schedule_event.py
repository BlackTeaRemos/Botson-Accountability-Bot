"""Slash commands for user-defined scheduled events."""
from __future__ import annotations

# pyright: reportUnusedFunction=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
import discord
from discord import app_commands
from ..services.persistence import PersistenceService
from ..services.reporting import schedulable_reports  # add registry import
from ..security import safe_send, has_admin


def RegisterScheduleCommands(bot: Any, storage: PersistenceService) -> None:
    """Register schedule slash commands."""
    schedule_group = app_commands.Group(name="schedule", description="Manage custom scheduled events")
    @schedule_group.command(name="create_anchored", description="Create a weekly anchored scheduled event")
    @app_commands.describe(
        report_type="Scheduled report type",
        expression="Interval expression (e.g., d2h4m30)",
    )
    async def CreateAnchoredEvent(interaction: discord.Interaction, report_type: str, expression: str):
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
            event_id = storage.add_event(
                channel_discord_id=cid,
                interval_minutes=0,
                command=report_type,
                schedule_anchor=anchor_l,
                schedule_expr=expression.strip().lower(),
            )
            await interaction.followup.send(
                f"Anchored event {event_id} created: {report_type} every '{expression}' (weekly).",
                ephemeral=True,
            )
        except Exception as e:
            await safe_send(interaction, f"Error creating anchored event: {e}", ephemeral=True)
    @CreateAnchoredEvent.autocomplete('report_type')
    async def report_type_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Suggest available scheduled report types."""
        suggestions = [
            app_commands.Choice(name=rt, value=rt)
            for rt in schedulable_reports
            if current.lower() in rt.lower()
        ]
        return suggestions[:25]

    @schedule_group.command(name="list", description="List scheduled events for this channel")
    async def ListEvents(interaction: discord.Interaction):
        cid = interaction.channel_id
        if cid is None:
            await interaction.response.send_message("Must be used in a channel.", ephemeral=True)
            return
        try:
            events = storage.list_events(channel_discord_id=cid)
            if not events:
                await interaction.response.send_message("No scheduled events found.", ephemeral=True)
                return
            lines: list[str] = []
            for ev in events:
                if ev.get('schedule_anchor') and ev.get('schedule_expr'):
                    lines.append(
                        f"ID {ev['id']}: anchor={ev['schedule_anchor']} expr={ev['schedule_expr']} -> '{ev['command']}' next at {ev['next_run']}"
                    )
                else:
                    lines.append(
                        f"ID {ev['id']}: every {ev['interval_minutes']}m -> '{ev['command']}' next at {ev['next_run']}"
                    )
            body = "\n".join(lines)
            await interaction.response.send_message(f"Scheduled events:\n{body}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error listing events: {e}", ephemeral=True)

    @schedule_group.command(name="remove", description="Remove a scheduled event by ID")
    async def RemoveEvent(interaction: discord.Interaction, event_id: int):
        try:
            success = storage.remove_event(event_id=event_id)
            if success:
                await interaction.response.send_message(f"Scheduled event {event_id} removed.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Event {event_id} not found.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error removing event: {e}", ephemeral=True)

    bot.tree.add_command(schedule_group)

    # ---- Interactive Manager UI ----

    class ExpressionPromptView(discord.ui.View):
        """Step 2: explain interval syntax and offer a button to open the private input modal."""
        def __init__(self, storage: PersistenceService, report_type: str, bot: Any, timeout: float | None = 180.0):
            super().__init__(timeout=timeout)
            self.storage = storage
            self.report_type = report_type
            self.bot = bot

        @discord.ui.button(label="Enter interval", style=discord.ButtonStyle.primary, custom_id="open_expression_modal_v1")
        async def open_expression(self, interaction: discord.Interaction, button: Any):
            try:
                await interaction.response.send_modal(ExpressionModal(self.storage, self.report_type, self.bot))
            except Exception as e:
                try:
                    await interaction.followup.send(f"Error: {e}", ephemeral=True)
                except Exception:
                    pass

    class ReportTypeWizardReportSelect(discord.ui.View):
        """Step 1: choose a report type; then ask for expression via message."""
        def __init__(self, storage: PersistenceService, report_types: list[str], bot: Any, timeout: float | None = 180.0):
            super().__init__(timeout=timeout)
            self.storage = storage
            self.bot = bot
            options = [discord.SelectOption(label=rt, value=rt) for rt in report_types] or [
                discord.SelectOption(label="No available reports", value="__none__", default=True, description="Nothing to select")
            ]
            self.select: Any = discord.ui.Select(
                placeholder="Choose report type",
                min_values=1,
                max_values=1,
                options=options,
                disabled=(len(options) == 1 and options[0].value == "__none__"),
                custom_id="report_type_select_v2",
            )
            self.add_item(self.select)

            async def _on_select(interaction: discord.Interaction) -> None:
                try:
                    if not self.select.values or self.select.values[0] == "__none__":
                        await interaction.response.send_message("No selectable reports.", ephemeral=True)
                        return
                    chosen = self.select.values[0]
                    # Show an explanation and a button to open a private modal for entering the interval
                    explanation = (
                        "Step 2 - Enter interval:\n"
                        "This schedule is anchored weekly (aligned to Monday 00:00 UTC).\n"
                        "Enter an offset using tokens: w (weeks), d (days), h (hours), m (minutes).\n"
                        "Examples: d2h4 (2 days, 4 hours), h12 (every 12 hours), w1 (every week).\n\n"
                        "Click the button below to open a private box to type the interval."
                    )
                    view = ExpressionPromptView(self.storage, chosen, self.bot)
                    await interaction.response.send_message(explanation, view=view, ephemeral=True)
                except Exception as e:
                    try:
                        await interaction.response.send_message(f"Error: {e}", ephemeral=True)
                    except Exception:
                        try:
                            await interaction.followup.send(f"Error: {e}", ephemeral=True)
                        except Exception:
                            pass

            self.select.callback = _on_select  # type: ignore[assignment]

    class ExpressionModal(discord.ui.Modal, title="Enter Expression"):
        def __init__(self, storage: PersistenceService, report_type: str, bot: Any):
            super().__init__()
            self.storage = storage
            self.report_type = report_type
            self.bot = bot
            self.expression: Any = discord.ui.TextInput(
                label="Expression (e.g., d2h4m30)",
                placeholder="d2h4m30",
                required=True,
                max_length=64,
            )
            self.add_item(self.expression)

        async def on_submit(self, interaction: discord.Interaction):
            expr = str(self.expression.value or "").strip().lower()
            if not expr:
                await interaction.response.send_message("Expression cannot be empty.", ephemeral=True)
                return
            # Proceed to mention type selection (ephemeral)
            view = MentionTypeSelectView(self.storage, self.report_type, expr, self.bot)
            await interaction.response.send_message("Choose mention type:", view=view, ephemeral=True)

    class MentionTypeSelectView(discord.ui.View):
        """Step 2: choose mention type; if user, prompt for user id via message; then create weekly event."""
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
                    # here/everyone require admin
                    if mt in ("here", "everyone"):
                        try:
                            if not has_admin(interaction):
                                await interaction.response.send_message("Only admins can use @here or @everyone.", ephemeral=True)
                                return
                        except Exception:
                            await interaction.response.send_message("Permission check failed.", ephemeral=True)
                            return
                    if mt == "user":
                        # Open private modal to capture user id or 'me'
                        await interaction.response.send_modal(UserIdModal(self.storage, self.report_type, self.expr))
                        return

                    target_user_id: str | None = None
                    if mt == "none":
                        target_user_id = str(interaction.user.id)  # default to creator even if not mentioned

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
                        mention_type=None if mt == 'none' else mt,
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
                    # If target not current user, require admin
                    if str(interaction.user.id) != raw:
                        try:
                            if not has_admin(interaction):
                                await interaction.response.send_message("Only admins can create schedules for others.", ephemeral=True)
                                return
                        except Exception:
                            await interaction.response.send_message("Permission check failed.", ephemeral=True)
                            return
                    target_user_id = raw

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

    class ScheduleManagerView(discord.ui.View):
        def __init__(self, storage: PersistenceService, items: list[dict[str, Any]], timeout: float | None = 120.0):
            super().__init__(timeout=timeout)
            self.storage = storage
            self.items_cache = items
            options: list[discord.SelectOption] = []
            for ev in items:
                if ev.get('schedule_anchor') and ev.get('schedule_expr'):
                    label = f"ID {ev['id']} | {ev['command']} | {ev['schedule_anchor']}:{ev['schedule_expr']}"
                else:
                    label = f"ID {ev['id']} | {ev['command']} | {ev['interval_minutes']}m"
                options.append(discord.SelectOption(label=label, value=str(ev['id'])))

            # Ensure select always has at least one option and a valid max_values
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

            # Ack select interactions to avoid 'interaction failed' banner
            async def _on_select(interaction: discord.Interaction) -> None:
                try:
                    await interaction.response.defer(ephemeral=True)
                except Exception:
                    # Already acknowledged or transient issue
                    pass
            # Bind the callback explicitly for dynamically created Select
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
                # No-op if disabled or placeholder selected
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

        # Removed Create Simple button

        @discord.ui.button(label="Create Anchored", style=discord.ButtonStyle.success, custom_id="schedule_create_anchored_v2")
        async def create_anchored(self, interaction: discord.Interaction, button: Any):
            view = ReportTypeWizardReportSelect(self.storage, list(schedulable_reports.keys()), bot)
            await interaction.response.send_message("Select a report type to schedule:", view=view, ephemeral=True)

    @schedule_group.command(name="manage", description="Open schedule manager UI")
    async def ManageSchedule(interaction: discord.Interaction):
        cid = interaction.channel_id
        if cid is None:
            await interaction.response.send_message("Must be used in a channel.", ephemeral=True)
            return
        items = storage.list_events(channel_discord_id=cid)
        view = ScheduleManagerView(storage, items)
        heading = "Schedule Manager" if items else "Schedule Manager - no events yet"
        await interaction.response.send_message(heading, view=view, ephemeral=True)

    # Keep references so static analyzers consider them used
    _registered_funcs = (CreateAnchoredEvent, ListEvents, RemoveEvent, ManageSchedule)
