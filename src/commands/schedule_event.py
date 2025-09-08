"""Slash commands for user-defined scheduled events (class-based, discoverable)."""

# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any
from .framework import CommandDefinition
from discord import app_commands


class ScheduleCommands(CommandDefinition):
    group_name = "schedule"
    group_description = "Manage custom scheduled events"

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:  # no inline commands
        return None

    def get_discovery_package(self) -> str | None:  # type: ignore[override]
        # Use explicit absolute package to be robust across import contexts
        return "src.commands.schedule_subcommands"

    @classmethod
    def register_with_services(cls, bot: Any, storage: Any) -> None:
        ctx: dict[str, Any] = {"storage": storage, "bot": bot}
        cls().register(bot, ctx)
