"""Slash commands for managing runtime configuration stored in DB.

Commands are restricted to users with Manage Guild permission. Token keys are blocked.
"""

from typing import Any, Awaitable, Callable
import discord

from ..services.settings import SettingsService, BLOCKED_KEYS


def _has_manage_guild(interaction: discord.Interaction) -> bool:
    perms = getattr(getattr(interaction, "user", None), "guild_permissions", None)
    return bool(perms and getattr(perms, "manage_guild", False))


def register_config_commands(
    bot: Any,
    settings: SettingsService,
    apply_runtime_settings: Callable[[], Awaitable[None]],
) -> None:
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
                discord.app_commands.Choice(name=k, value=k)  # type: ignore[attr-defined]
                for k in filtered[:20]
            ]
            return results
        except Exception:
            return []
    @bot.tree.command(name="config_list", description="List configurable keys (DB)")
    async def config_list(interaction: discord.Interaction):
        try:
            if not interaction.guild_id:
                await interaction.response.send_message("Use this in a guild.", ephemeral=True)
                return
            if not _has_manage_guild(interaction):
                await interaction.response.send_message("Missing Manage Server permission.", ephemeral=True)
                return
            keys = settings.list_keys()
            if not keys:
                await interaction.response.send_message("No settings set.", ephemeral=True)
                return
            await interaction.response.send_message(
                "Keys:\n" + "\n".join(sorted(keys)), ephemeral=True
            )
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)
        _ = config_list

    @bot.tree.command(name="config_get", description="Get a setting value (DB)")
    @discord.app_commands.describe(key="Setting key")
    @discord.app_commands.autocomplete(key=key_autocomplete)
    async def config_get(interaction: discord.Interaction, key: str):
        try:
            if not interaction.guild_id:
                await interaction.response.send_message("Use this in a guild.", ephemeral=True)
                return
            if not _has_manage_guild(interaction):
                await interaction.response.send_message("Missing Manage Server permission.", ephemeral=True)
                return
            lowered = key.lower()
            if lowered in {k.lower() for k in BLOCKED_KEYS}:
                await interaction.response.send_message("This key is blocked.", ephemeral=True)
                return
            val = settings.get(key)
            if val is None:
                await interaction.response.send_message("<unset>", ephemeral=True)
                return
            import json
            await interaction.response.send_message(
                f"```json\n{json.dumps(val, indent=2, ensure_ascii=False)}\n```",
                ephemeral=True,
            )
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)
        _ = config_get

    @bot.tree.command(name="config_set", description="Set a setting value (JSON or primitive)")
    @discord.app_commands.describe(key="Setting key", value="JSON or primitive value")
    @discord.app_commands.autocomplete(key=key_autocomplete)
    async def config_set(interaction: discord.Interaction, key: str, value: str):
        try:
            if not interaction.guild_id:
                await interaction.response.send_message("Use this in a guild.", ephemeral=True)
                return
            if not _has_manage_guild(interaction):
                await interaction.response.send_message("Missing Manage Server permission.", ephemeral=True)
                return
            lowered = key.lower()
            if lowered in {k.lower() for k in BLOCKED_KEYS}:
                await interaction.response.send_message("This key is blocked.", ephemeral=True)
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
            await interaction.response.send_message("Saved and applied.", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)
        _ = config_set

    @bot.tree.command(name="config_delete", description="Delete a setting")
    @discord.app_commands.describe(key="Setting key")
    @discord.app_commands.autocomplete(key=key_autocomplete)
    async def config_delete(interaction: discord.Interaction, key: str):
        try:
            if not interaction.guild_id:
                await interaction.response.send_message("Use this in a guild.", ephemeral=True)
                return
            if not _has_manage_guild(interaction):
                await interaction.response.send_message("Missing Manage Server permission.", ephemeral=True)
                return
            lowered = key.lower()
            if lowered in {k.lower() for k in BLOCKED_KEYS}:
                await interaction.response.send_message("This key is blocked.", ephemeral=True)
                return
            removed = settings.delete(key)
            if removed:
                await apply_runtime_settings()
            await interaction.response.send_message("Deleted and applied." if removed else "Not found.", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)
        _ = config_delete

    @bot.tree.command(name="config_available", description="List available configuration keys")
    async def config_available(interaction: discord.Interaction):
        try:
            if not interaction.guild_id:
                await interaction.response.send_message("Use this in a guild.", ephemeral=True)
                return
            if not _has_manage_guild(interaction):
                await interaction.response.send_message("Missing Manage Server permission.", ephemeral=True)
                return
            items = settings.get_available_with_meta()
            if not items:
                await interaction.response.send_message("No settings are available.", ephemeral=True)
                return
            lines = [f"{it['key']} ({it['type']}): {it['description']}".strip() for it in items]
            body = "\n".join(lines)
            await interaction.response.send_message(body[:1900], ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)
        _ = config_available

