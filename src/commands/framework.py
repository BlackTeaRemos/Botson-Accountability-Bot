"""Single-class framework for Discord app commands.

This module intentionally exposes one class, CommandDefinition, to serve as a
general base for both top-level command groups and sub-command providers.

Derive your commands from CommandDefinition and override:
    - group_name (str | None): set to a string to define a top-level group name;
        leave as None for sub-command providers that attach into a parent's group.
    - group_description (str): optional, defaults to group_name.
    - define(self, group, ctx): attach one or more slash commands to the provided
        app_commands.Group using decorators.

Top-level groups call register(bot, ctx, package=...) to create their group,
attach their own commands, discover and attach sub-commands from a package, and
add the group to bot.tree.

No standalone helper functions are provided by design; discovery and wiring are
encapsulated as (class)methods on CommandDefinition to keep the surface small.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Type
from abc import ABC, abstractmethod
import importlib
import inspect
import logging
import pkgutil

from discord import app_commands

# Public logger for discovery/registration diagnostics
logger = logging.getLogger(__name__)

class CommandDefinition(ABC):
    """General base class for command groups and sub-commands.

    Usage patterns:
      1) Top-level group
         class ReportCommands(CommandDefinition):
             group_name = "report"
             group_description = "Reporting commands"

             def define(self, group, ctx):
                 @group.command(name="weekly", description="Weekly report")
                 async def weekly(interaction: discord.Interaction):
                     ...

         # At startup
         ReportCommands().register(bot, ctx, package="your_pkg.commands.report")

      2) Sub-commands only (no group)
         class ExtraReport(CommandDefinition):
             # group_name left as None -> treated as sub-command provider
             def define(self, group, ctx):
                 @group.command(name="embed", description="Embed report")
                 async def embed(interaction: discord.Interaction):
                     ...

    Contract:
      - group_name: str | None. If set, register() creates a Group and adds it
        to the bot tree. If None, instances are used only as discovered
        sub-command providers and must not call register() directly.
      - define(group, ctx): attach slash commands to the provided group.
    """

    # Set this in subclasses to create a top-level slash group; None => sub-provider
    group_name: Optional[str] = None
    group_description: str = ""

    @abstractmethod
    def define(self, group: app_commands.Group, ctx: Mapping[str, Any]) -> None:
        """Attach one or more slash commands to the provided group."""
        raise NotImplementedError

    # ----- Convenience helpers for context and discovery (methods; no free functions) -----
    def get_discovery_package(self) -> Optional[str]:
        """Return fully-qualified package path to discover sub-commands from.

        Override in a top-level group to enable automatic discovery without
        passing a package string to register(). Default is None (no discovery).
        """
        return None
    @staticmethod
    def ctx_require(ctx: Mapping[str, Any], key: str) -> Any:
        """Return required context value or raise KeyError."""
        if key not in ctx:
            raise KeyError(f"Missing required context key: {key}")
        return ctx[key]

    @classmethod
    def _discover_from_package(cls: Type["CommandDefinition"], package: str) -> list["CommandDefinition"]:
        """Import all modules in a package and instantiate subclasses of this class."""
        try:
            pkg = importlib.import_module(package)
        except Exception as e:  # pragma: no cover - import error path
            logger.error("Failed to import package '%s': %s", package, e)
            return []

        pkg_path_list = getattr(pkg, "__path__", None)
        if not pkg_path_list:
            logger.warning("Package '%s' has no __path__; nothing to discover.", package)
            return []

        found: list[CommandDefinition] = []
        for mod_info in pkgutil.iter_modules(pkg_path_list):
            if not mod_info.ispkg and mod_info.name.startswith("_"):
                continue
            full_name = f"{package}.{mod_info.name}"
            try:
                mod = importlib.import_module(full_name)
            except Exception as e:  # pragma: no cover - import error path
                logger.warning("Skipping module '%s' (import failed): %s", full_name, e)
                continue
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if not issubclass(obj, CommandDefinition) or obj is CommandDefinition:
                    continue
                try:
                    sig = inspect.signature(obj)
                    if len(sig.parameters) == 0:
                        instance = obj()  # type: ignore[call-arg]
                    else:
                        logger.debug("Skipping %s: non-empty constructor.", obj)
                        continue
                    found.append(instance)
                except Exception as e:  # pragma: no cover - instantiation error path
                    logger.debug("Failed to instantiate %s: %s", obj, e)
                    continue
        return found

    # ----- Main entrypoint for groups -----
    def register(
        self,
        bot: Any,
        ctx: Mapping[str, Any],
        *,
        package: Optional[str] = None,
    ) -> Optional[app_commands.Group]:
        """Create and register a slash command group and its sub-commands.

        If this instance has group_name set, a new group is created and added to
        the bot tree. The instance's define() is called to attach commands, and
        optionally sub-command providers discovered from `package` are attached.

        If group_name is None, this method returns None and performs no action.
        """
        if not self.group_name:
            # Sub-command providers should not be registered directly
            return None

        group = app_commands.Group(name=self.group_name, description=self.group_description or self.group_name)

        if "bot" not in ctx:
            ctx = {**ctx, "bot": bot}

        # Register commands implemented by this class
        self.define(group, ctx)

        discovery_pkg = package or self.get_discovery_package()
        if discovery_pkg:
            providers = self._discover_from_package(discovery_pkg)
            # Only attach providers that are sub-providers (group_name is None)
            providers = [p for p in providers if not p.group_name]
            providers.sort(key=lambda p: p.__class__.__name__)
            for prov in providers:
                prov.define(group, ctx)
                logger.info("Registered sub-commands from %s into /%s", prov.__class__.__name__, self.group_name)

        bot.tree.add_command(group)
        return group


__all__ = ["CommandDefinition"]
