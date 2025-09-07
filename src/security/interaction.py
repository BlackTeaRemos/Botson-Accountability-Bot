"""Interaction safety helpers for Discord commands.
"""
from __future__ import annotations

import discord


async def safe_send(interaction: discord.Interaction, content: str, *, ephemeral: bool = True) -> None:
    """Send a response or follow-up safely based on interaction state.

    Tries interaction.response.send_message first if not done, otherwise followup.
    Swallows secondary exceptions to avoid raising in handlers.
    """
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(content, ephemeral=ephemeral)
        else:
            await interaction.followup.send(content, ephemeral=ephemeral)
    except Exception:
        try:
            await interaction.followup.send(content, ephemeral=ephemeral)
        except Exception:
            pass


async def safe_defer(interaction: discord.Interaction, *, ephemeral: bool = True, thinking: bool = True) -> None:
    """Safely defer an interaction; ignore if already acknowledged."""
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
    except Exception:
        # Ignore; best-effort only
        pass
