"""Slash commands for managing runtime configuration stored in DB.

Commands are restricted to users with Manage Guild permission. Token keys are blocked.
"""

from typing import Any, Awaitable, Callable
import discord
from discord import app_commands

from ..services.settings import SettingsService, BLOCKED_KEYS
from ..security import has_manage_guild, require_guild, require_manage_guild, safe_send


def RegisterConfigCommands(
    bot: Any,
    settings: SettingsService,
    apply_runtime_settings: Callable[[], Awaitable[None]],
) -> None:
    """Register configuration management commands on the bot.

    Args:
        bot: The Discord bot instance.
        settings: The settings service instance.
        apply_runtime_settings: Function to apply runtime settings.

    Returns:
        None

    Example:
        RegisterConfigCommands(bot, settings, apply_settings)
    """
    # Autocomplete helper for keys (available + existing)
    from typing import List as _List, Any as _Any

    async def key_autocomplete(interaction: discord.Interaction, current: str) -> _List[_Any]:
        try:
            available = settings.list_available_keys()
            existing = settings.list_keys()
            pool = sorted({*available, *existing})
            cur = (current or "").lower()
            blocked = {b.lower() for b in BLOCKED_KEYS}
            filtered = [k for k in pool if cur in k.lower() and k.lower() not in blocked]
            results: list[Any] = [
                app_commands.Choice(name=k, value=k)  # type: ignore[attr-defined]
                for k in filtered[:20]
            ]
            return results
        except Exception:
            return []

    # Define the /config group
    config_group = app_commands.Group(name="config", description="Manage bot configuration")

    @config_group.command(name="list", description="List keys that are currently set in DB")
    @require_guild
    @require_manage_guild
    async def ConfigList(interaction: discord.Interaction):
        try:
            keys = settings.list_keys()
            if not keys:
                await safe_send(interaction, "No settings set.", ephemeral=True)
                return
            await safe_send(interaction, "Keys:\n" + "\n".join(sorted(keys)), ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @config_group.command(name="available", description="List available configuration keys")
    @require_guild
    @require_manage_guild
    async def ConfigAvailable(interaction: discord.Interaction):
        try:
            items = settings.get_available_with_meta()
            if not items:
                await safe_send(interaction, "No settings are available.", ephemeral=True)
                return
            lines = [f"{it['key']} ({it['type']}): {it['description']}".strip() for it in items]
            body = "\n".join(lines)
            await safe_send(interaction, body[:1900], ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @config_group.command(name="get", description="Get a setting value (DB)")
    @app_commands.describe(key="Setting key")
    @app_commands.autocomplete(key=key_autocomplete)
    @require_guild
    @require_manage_guild
    async def ConfigGet(interaction: discord.Interaction, key: str):
        try:
            lowered = key.lower()
            if lowered in {k.lower() for k in BLOCKED_KEYS}:
                await safe_send(interaction, "This key is blocked.", ephemeral=True)
                return
            val = settings.get(key)
            if val is None:
                await safe_send(interaction, "<unset>", ephemeral=True)
                return
            import json
            await safe_send(interaction, f"```json\n{json.dumps(val, indent=2, ensure_ascii=False)}\n```", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @config_group.command(name="set", description="Set a setting value (JSON or primitive)")
    @app_commands.describe(key="Setting key", value="JSON or primitive value")
    @app_commands.autocomplete(key=key_autocomplete)
    @require_guild
    @require_manage_guild
    async def ConfigSet(interaction: discord.Interaction, key: str, value: str):
        try:
            lowered = key.lower()
            if lowered in {k.lower() for k in BLOCKED_KEYS}:
                await safe_send(interaction, "This key is blocked.", ephemeral=True)
                return
            # Try to parse as JSON; fallback to raw string
            import json
            parsed: Any
            try:
                parsed = json.loads(value)
            except Exception:
                # try common literals
                if value.lower() in {"true", "false"}:
                    parsed = value.lower() == "true"
                else:
                    try:
                        if "." in value:
                            parsed = float(value)
                        else:
                            parsed = int(value)
                    except Exception:
                        parsed = value
            settings.set(key, parsed)
            await apply_runtime_settings()
            await safe_send(interaction, "Saved and applied.", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @config_group.command(name="delete", description="Delete a setting")
    @app_commands.describe(key="Setting key")
    @app_commands.autocomplete(key=key_autocomplete)
    @require_guild
    @require_manage_guild
    async def ConfigDelete(interaction: discord.Interaction, key: str):
        try:
            lowered = key.lower()
            if lowered in {k.lower() for k in BLOCKED_KEYS}:
                await safe_send(interaction, "This key is blocked.", ephemeral=True)
                return
            removed = settings.delete(key)
            if removed:
                await apply_runtime_settings()
            await safe_send(interaction, "Deleted and applied." if removed else "Not found.", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)

    bot.tree.add_command(config_group)

    # Keep explicit references for static analyzers
    _registered_config_commands: dict[str, object] = {
        "list": ConfigList,
        "available": ConfigAvailable,
        "get": ConfigGet,
        "set": ConfigSet,
        "delete": ConfigDelete,
    }
    _ = _registered_config_commands

