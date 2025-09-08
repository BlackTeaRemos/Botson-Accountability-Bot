"""Reporting command group using the CommandDefinition base with discovery.
"""

# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from typing import Any
from .framework import CommandDefinition
from discord import app_commands


class ReportingCommands(CommandDefinition):
    group_name = "report"
    group_description = "Reporting commands"

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:  # no inline commands
        return None

    def get_discovery_package(self) -> str | None:  # type: ignore[override]
        return f"{__package__}.report_subcommands" if __package__ else "src.commands.report_subcommands"

    @classmethod
    def register_with_services(
        cls,
        bot: Any,
        storage: Any,
        reporting: Any,
        channels: Any,
        config: Any,
    ) -> None:
        ctx: dict[str, Any] = {
            "storage": storage,
            "reporting": reporting,
            "channels": channels,
            "config": config,
        }
        cls().register(bot, ctx)
