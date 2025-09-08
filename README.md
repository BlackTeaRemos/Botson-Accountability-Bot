# Accountability Bot (Event-Driven Rework Scaffold)

## Quick Start (Local)
1. Python 3.12+
2. `python -m venv .venv && . .venv/Scripts/Activate.ps1` (Windows PowerShell)
3. `pip install -r requirements.txt`
4. Set token: `$env:DISCORD_TOKEN="YOUR_TOKEN_HERE"`
5. Run: `python run.py`

## Docker Run (Single Container)
Build and run manually:
```
docker build -t accountability-bot .
# Insert your key in the command below (DO NOT COMMIT IT):
docker run -d --name accountability-bot -e DISCORD_TOKEN=YOUR_TOKEN_HERE -v bot_data:/data accountability-bot
```

## Docker Compose (Recommended)
Edit `docker-compose.yml` and replace this line:
```
DISCORD_TOKEN: "REPLACE_WITH_YOUR_DISCORD_BOT_TOKEN"  # <- INSERT YOUR TOKEN HERE
```
Then start:
```
docker compose up -d --build
```
(Compose will create a named volume `bot_data` storing `bot.db`.)

Alternatively use an `.env` file:
1. Copy `.env.example` to `.env`
2. Put your token: `DISCORD_TOKEN=YOUR_TOKEN_HERE`
3. In `docker-compose.yml` comment the inline DISCORD_TOKEN and uncomment:
```
# env_file:
#   - .env
```
4. Run `docker compose up -d --build`

## Environment Variables
- `DISCORD_TOKEN` (required)
- `BOT_DB_PATH` (default `/data/bot.db` inside container or `bot.db` locally)
- `BACKFILL_DEFAULT_DAYS` (default 30)
- `USE_DB_ONLY` (default false)
- `GUILD_ID` (optional; speeds up slash command sync in a primary guild)
- `DAILY_GOAL_TASKS` (default 5)

Scheduler (embed posts):
- `SCHEDULED_REPORTS_ENABLED` (default true if unset/empty) - enable the background scheduler
- `SCHEDULED_REPORT_INTERVAL_MINUTES` (default 60) - minutes between posts
- `SCHEDULED_REPORT_CHANNEL_IDS` (optional CSV of channel IDs) - if set, only these channels get posts; otherwise, all registered channels are used

## Runtime Configuration via Discord

The bot supports runtime-editable configuration persisted in the database (safe keys only; the Discord token is never stored and cannot be edited via commands).

Slash commands (Manage Server permission required):

- /config_list - list keys stored in DB
- /config_get key:<name> - show current value
- /config_set key:<name> value:<json-or-primitive> - set a value and apply immediately
- /config_delete key:<name> - remove a key and re-apply defaults

Examples of values:

- true, false
- 15, 60
- "UTC"
- [123456789012345678, 234567890123456789]

Blocked keys: DISCORD_TOKEN, discord_token, token.

On changes, the weekly report scheduler is started/stopped/reconfigured to reflect new settings right away.

## Current Status
Scaffold includes: migrations, event bus, channel registration, message ingestion, habit parsing (raw scores), weekly report (image and embed), and a configurable scheduler for periodic embed posts.

## License
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Botson is licensed under the Apache License 2.0. This permissive license allows commercial use, modifications, and redistribution while providing explicit patent protection for contributors and users. It includes a patent retaliation clause to deter patent misuse.

By contributing, you agree to license your work under Apache-2.0 and grant maintainers the right to relicense future versions under other OSI-approved licenses if needed (see CONTRIBUTING.md for details).

## Safety Note
## Development

Run tests locally:

```
pip install -r requirements.txt
pytest -q
```
Never commit your real Discord bot token. Use `.env`, compose environment section, or secret management.

## Command Framework (Class-based)

This project uses a small class-based framework for Discord slash commands.

Key ideas:
- One base class: `CommandDefinition` in `src/commands/framework.py`.
- A top-level command group is a subclass with `group_name` set (e.g., `"report"`).
- Sub-commands are subclasses with `group_name = None` placed in a sibling package (one class per file).
- Group classes discover and attach sub-commands automatically from a package.
- All wiring happens via class methods; no free functions.

### Define a group

File: `src/commands/reporting.py`

```python
from typing import Any
from discord import app_commands
from .framework import CommandDefinition

class ReportingCommands(CommandDefinition):
	group_name = "report"
	group_description = "Reporting commands"

	def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
		# No inline commands here; see sub-commands in report_subcommands/*
		return None

	def get_discovery_package(self) -> str | None:
		return "src.commands.report_subcommands"

	@classmethod
	def register_with_services(cls, bot: Any, storage: Any, reporting: Any, channels: Any, config: Any) -> None:
		ctx = {"storage": storage, "reporting": reporting, "channels": channels, "config": config}
		cls().register(bot, ctx)
```

### Define a sub-command

File: `src/commands/report_subcommands/weekly.py`

```python
from typing import Any
import discord
from discord import app_commands
from ..framework import CommandDefinition

class ReportWeekly(CommandDefinition):
	group_name = None  # attaches into /report

	def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
		storage = ctx["storage"]

		@group.command(name="weekly", description="Weekly report")
		async def _cmd(interaction: discord.Interaction):
			await interaction.response.send_message("Weekly report coming up…", ephemeral=True)
```

Place each sub-command in its own file inside the discovery package. The group’s `get_discovery_package()` must point at that package.

### Register at startup

Register groups via classmethods in `src/bot/startup.py`:

```python
from ..commands import reporting as reporting_commands
from ..commands import debug as debug_commands
from ..commands.schedule_event import ScheduleCommands

def RegisterBotCommands(bot: discord.Client) -> None:
	reporting_commands.ReportingCommands.register_with_services(bot, storage, reporting, channels, config)
	debug_commands.DebugCommands.register_with_services(bot, storage, make_generate_random_user_recent(storage))
	ScheduleCommands.register_with_services(bot, storage)
```

### Context contract

`register_with_services(...)` builds a plain `dict[str, Any]` (the ctx) that is provided to all sub-commands. Access services via keys, e.g. `ctx["storage"]`. The framework automatically adds `ctx["bot"]` if missing.

### Discovery rules

- Group class calls `self.register(bot, ctx)`.
- `register()` creates the `app_commands.Group`, calls the group's `define()`, then scans the discovery package for subclasses of `CommandDefinition` with `group_name=None`.
- Each discovered provider's `define()` is called with the same `group` and `ctx`, so they can attach commands using `@group.command(...)`.

### Adding a new command group

1. Create `src/commands/<name>.py` with a `CommandDefinition` subclass and `get_discovery_package()`.
2. Create `src/commands/<name>_subcommands/` and add one class-per-file implementing `define()`.
3. Register in startup with a `register_with_services(...)` classmethod.

