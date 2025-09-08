# Commands module

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

