"""Event handler registration modules.
"""

from typing import Callable, cast

from .message_ingestion import register as _register_message_ingestion

from ..core.events import EventBus
from ..services.persistence import PersistenceService
from ..services.habit_parser import HabitParser

register_message_ingestion: Callable[[EventBus, PersistenceService, HabitParser], None] = cast(
	Callable[[EventBus, PersistenceService, HabitParser], None], _register_message_ingestion
)
