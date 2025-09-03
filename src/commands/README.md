# Commands module

This folder encapsulates all Discord slash commands. Commands are organized as grouped slash commands using discord.py `app_commands.Group` for a clean UX and reliable autocomplete.

## Current groups

```
/report
  weekly
  embed
  clear_week
  backfill
  style set

/config
  list
  available
  get
  set
  delete

/debug
  add_score
  remove_score
  user_info
  purge_bad_dates
  generate_user

/channel
  register
```

## How commands are registered

Each module exposes a `register_*_commands(bot, ...) -> None` function. The function defines a group, declares subcommands, and calls `bot.tree.add_command(group)`.

`bot_main.register_bot_commands()` imports these modules and calls the registration functions during startup, before syncing the command tree.

## Authoring commands: effective patterns

Typing indicator and followups

```
await interaction.response.defer(thinking=True, ephemeral=True)
# Perform work
await interaction.followup.send("Done")
```

Error handling

```
try:
    ...
except Exception as e:
    if not interaction.response.is_done():
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)
    else:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)
```

Autocomplete and choices

```
from discord import app_commands

async def key_autocomplete(interaction, current: str):
    items = ["alpha", "beta", "gamma"]
    cur = (current or "").lower()
    filtered = [x for x in items if cur in x.lower()]
    return [app_commands.Choice(name=x, value=x) for x in filtered[:20]]

@group.command(name="get")
@app_commands.describe(key="Setting key")
@app_commands.autocomplete(key=key_autocomplete)
async def get(interaction, key: str):
    ...
```

Permissions

```
def _has_manage_guild(interaction) -> bool:
    perms = getattr(getattr(interaction, "user", None), "guild_permissions", None)
    return bool(perms and getattr(perms, "manage_guild", False))

if not _has_manage_guild(interaction):
    await interaction.response.send_message("Missing Manage Server permission.", ephemeral=True)
    return
```

Minimal template

```
# src/commands/feature_x.py
from typing import Any
import discord
from discord import app_commands


def register_feature_x_commands(bot: Any, service: Any) -> None:
    group = app_commands.Group(name="featurex", description="Feature X commands")

    @group.command(name="do", description="Run Feature X action")
    async def do_cmd(interaction: discord.Interaction, arg: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = service.do(arg)
        await interaction.followup.send(f"Result: {result}")

    bot.tree.add_command(group)
```

Implementation notes

- Prefer ephemeral responses for admin/maintenance commands.
- For large outputs, split across embed fields or send as files where appropriate.