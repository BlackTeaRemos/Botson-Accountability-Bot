"""Commands package for the bot.

Each module exposes a register_... function that attaches slash commands to the provided
bot instance.
"""

__all__ = [
    "reporting",
    "debug",
    "channels",
    "utils",
    "config",
    "schedule_event",
]

from . import reporting
from . import debug
from . import channels
from . import utils
from . import config
from . import schedule_event
