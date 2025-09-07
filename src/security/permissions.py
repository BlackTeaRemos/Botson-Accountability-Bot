"""Permission helpers and decorators for Discord interactions.
"""
from __future__ import annotations

from typing import Awaitable, Callable, TypeVar, ParamSpec, cast
import functools
import discord

from .interaction import safe_send

Params = ParamSpec("Params")
ResultT = TypeVar("ResultT")


def has_manage_guild(interaction: discord.Interaction) -> bool:
    """Return True if the user has the Manage Guild permission.

    Args:
        interaction (discord.Interaction): The Discord interaction.

    Returns:
        bool: True if user has manage_guild, otherwise False.
    """
    perms = getattr(getattr(interaction, "user", None), "guild_permissions", None)
    return bool(perms and getattr(perms, "manage_guild", False))


def has_admin(interaction: discord.Interaction) -> bool:
    """Return True if the user has the Administrator permission.

    Args:
        interaction (discord.Interaction): The Discord interaction.

    Returns:
        bool: True if user has administrator, otherwise False.
    """
    perms = getattr(getattr(interaction, "user", None), "guild_permissions", None)
    return bool(perms and getattr(perms, "administrator", False))


def require_guild(func: Callable[Params, Awaitable[ResultT]]) -> Callable[Params, Awaitable[ResultT | None]]:
    """Decorator to require the command be used in a guild context.

    Sends an ephemeral message and returns early if `interaction.guild_id` is falsy.
    """

    @functools.wraps(func)
    async def wrapper(*args: Params.args, **kwargs: Params.kwargs) -> ResultT | None:  # type: ignore[override]
        interaction = cast(discord.Interaction, args[0])
        if not getattr(interaction, "guild_id", None):
            await safe_send(interaction, "Use this in a guild.", ephemeral=True)
            return None
        return await func(*args, **kwargs)

    return wrapper


def require_manage_guild(func: Callable[Params, Awaitable[ResultT]]) -> Callable[Params, Awaitable[ResultT | None]]:
    """Decorator to require Manage Guild permission on the invoking user."""

    @functools.wraps(func)
    async def wrapper(*args: Params.args, **kwargs: Params.kwargs) -> ResultT | None:  # type: ignore[override]
        interaction = cast(discord.Interaction, args[0])
        if not has_manage_guild(interaction):
            await safe_send(interaction, "Missing Manage Server permission.", ephemeral=True)
            return None
        return await func(*args, **kwargs)

    return wrapper


def require_admin(func: Callable[Params, Awaitable[ResultT]]) -> Callable[Params, Awaitable[ResultT | None]]:
    """Decorator to require Administrator permission on the invoking user."""

    @functools.wraps(func)
    async def wrapper(*args: Params.args, **kwargs: Params.kwargs) -> ResultT | None:  # type: ignore[override]
        interaction = cast(discord.Interaction, args[0])
        if not has_admin(interaction):
            await safe_send(interaction, "Missing Administrator permission.", ephemeral=True)
            return None
        return await func(*args, **kwargs)

    return wrapper
