# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""/debug command group and sub-command wiring using the CommandDefinition base.

The main group is defined here. Individual sub-commands live in
src/commands/debug_subcommands/*.py as CommandDefinition subclasses with
group_name=None. They are auto-discovered during registration.
"""

from typing import Any, Callable, Dict
from discord import app_commands
from .framework import CommandDefinition


class DebugCommands(CommandDefinition):
    group_name = "debug"
    group_description = "Developer utilities"

    # This class defines no inline commands; all are in debug_subcommands/*
    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        return None

    def get_discovery_package(self) -> str | None:  # type: ignore[override]
        # Discover sub-commands from sibling package
        return f"{__package__}.debug_subcommands" if __package__ else "src.commands.debug_subcommands"

    @classmethod
    def register_with_services(
        cls,
        bot: Any,
        storage: Any,
        generate_random_user_recent: Callable[..., Dict[str, Any]],
    ) -> None:
        """Register /debug by discovering sub-commands via the class's discovery package.

        Args:
            bot: Discord client/bot instance.
            storage: Persistence service instance.
            generate_random_user_recent: Callable to generate test user data.
        """
        ctx: dict[str, Any] = {
            "storage": storage,
            "generate_random_user_recent": generate_random_user_recent,
        }
        cls().register(bot, ctx)
