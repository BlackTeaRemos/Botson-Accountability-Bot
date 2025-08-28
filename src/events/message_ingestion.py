"""Message ingestion & habit parsing event handlers.

Extracted from `bot_main.register_event_handlers` to keep startup wiring slim.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any

from ..core.events import EventBus, Event

# Use Any for loose dependency injection typing so the analyzer doesn't treat
# these names as variables in type expressions.
Storage = Any
HabitParserType = Any


def register(bus: EventBus, storage: Storage, habit_parser: HabitParserType) -> None:
    """Attach handlers for message ingestion & habit parsing.

    Args:
        bus: The shared EventBus instance.
        storage: Persistence service.
        habit_parser: Parser service.
    """

    async def handle_message(event: Event):
        if event.type not in ("MessageReceived", "MessageEdited"):
            return
        cid = event.payload["channel_id"]
        if not storage.is_channel_registered(cid):
            return
        if event.type == "MessageReceived":
            storage.insert_message(
                discord_message_id=event.payload["discord_message_id"],
                channel_id=cid,
                author_id=event.payload["author_id"],
                author_display=event.payload.get("author_display", ""),
                created_at=event.payload["created_at"],
                content=event.payload["content"],
            )
        parsed = habit_parser.parse_message(
            event.payload["content"],
            datetime.fromisoformat(event.payload["created_at"].replace('Z', '')),
        )
        if parsed and parsed.get("extracted_date"):
            storage.update_habit_parse(
                event.payload["discord_message_id"],
                parsed["raw_bracket_count"],
                parsed["filled_bracket_count"],
                parsed["confidence"],
                parsed["extracted_date"],
            )
            storage.insert_or_replace_message_score(
                discord_message_id=event.payload["discord_message_id"],
                user_id=event.payload["author_id"],
                date=parsed["extracted_date"],
                channel_discord_id=cid,
                raw_ratio=parsed["raw_ratio"],
                filled=parsed["filled_bracket_count"],
                total=parsed["raw_bracket_count"],
            )
            storage.recompute_daily_scores(
                channel_discord_id=cid,
                date=parsed["extracted_date"]
            )

    bus.subscribe("MessageReceived", handle_message)
    bus.subscribe("MessageEdited", handle_message)
