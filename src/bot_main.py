"""Discord bot entrypoint: wires configuration, services, slash commands, and event handling."""

import discord
import logging
from discord.ext import commands


from .bot import startup
from .commands import debug_functions as debug_functions
from .security import validate_discord_token

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)

report_scheduler: object | None = None
event_scheduler: object | None = None

bot = commands.Bot(command_prefix="!", intents=intents)


async def UpdateRuntimeConfiguration() -> None:
    """Compatibility wrapper that delegates to `src.bot.startup.UpdateRuntimeConfiguration`."""
    await startup.UpdateRuntimeConfiguration(bot)


def Run():
    """Main entry to launch the Discord bot after environment validation.
    Raises:
        SystemExit: If the Discord token is not properly configured

    Example:
        Run()  # Launches the bot if token is valid
    """
    token = startup.config.discord_token  # type: ignore
    validate_discord_token(token)
    token_parts = token.split('.')
    masked_token = token_parts[0][:4] + "..." + token_parts[-1][-4:]
    print(f"[Startup] Using token (masked): {masked_token}")

    startup.RegisterRuntime(bot)
    bot.run(token)

GenerateRandomUserRecent = debug_functions.make_generate_random_user_recent(startup.storage)
JsonDumpsCompact = startup.JsonDumpsCompact

def Run() -> None:
    """Compatibility wrapper around startup.Run to validate token and start the bot."""
    token = startup.config.discord_token  # type: ignore
    validate_discord_token(token)
    startup.Run(bot)


if __name__ == "__main__":
    Run()
