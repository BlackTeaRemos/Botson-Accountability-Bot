from __future__ import annotations

import asyncio
from sqlalchemy.orm import Session

from src.core.events import EventBus
from src.events.message_ingestion import register
from src.services.habit_parser import HabitParser
from src.services.persistence import PersistenceService
from src.db.connection import Database
from src.db.models import Message, HabitMessageScore, HabitDailyScore


async def _emit(bus: EventBus, type: str, payload: dict[str, object]) -> None:
    await bus.Emit(type, payload)


def test_ingestion_parses_and_scores(db: Database, seed_channel: int) -> None:
    bus = EventBus()
    storage = PersistenceService(db)
    parser = HabitParser(bus)
    register(bus, storage, parser)

    payload: dict[str, object] = {
        "discord_message_id": 9991,
        "channel_id": seed_channel,
        "author_id": 55,
        "author_display": "u",
        "created_at": "2024-01-10T10:00:00",
        "content": "[x] [ ] [x] Jan 10",
    }

    asyncio.get_event_loop().run_until_complete(_emit(bus, "MessageReceived", payload))

    # Verify message row and scores exist
    session: Session = db.GetSession()
    try:
        msg = (
            session.query(Message)
            .filter(Message.discord_message_id == str(payload["discord_message_id"]))
            .first()
        )
        assert msg is not None
        mscore = session.query(HabitMessageScore).filter(HabitMessageScore.message_id == msg.id).first()
        assert mscore is not None
        dscore = session.query(HabitDailyScore).filter(
            HabitDailyScore.channel_id == msg.channel_id,
            HabitDailyScore.date == "2024-01-10",
            HabitDailyScore.user_id == str(payload["author_id"]),
        ).first()
        assert dscore is not None
    finally:
        session.close()
