from __future__ import annotations

from src.db.connection import Database
from src.services.persistence import PersistenceService
# No need to import AppConfig or EventScheduler for persistence roundtrip tests


def test_add_event_no_mention_defaults_none(db: Database, seed_channel: int):
    storage = PersistenceService(db)
    # Add event with mention_type='none'
    eid = storage.add_event(
        channel_discord_id=seed_channel,
        interval_minutes=0,
        command="weekly_image",
        schedule_anchor="week",
        schedule_expr="d1",
        target_user_id=None,
        mention_type='none',
    )
    assert isinstance(eid, int)
    events = storage.list_events(seed_channel)
    assert events
    ev = next(e for e in events if e['id'] == eid)
    assert ev['mention_type'] == 'none'
    assert ev['target_user_id'] is None


def test_add_event_user_mention_roundtrip(db: Database, seed_channel: int):
    storage = PersistenceService(db)
    eid = storage.add_event(
        channel_discord_id=seed_channel,
        interval_minutes=0,
        command="weekly_image",
        schedule_anchor="week",
        schedule_expr="d1",
        target_user_id="1234567890",
        mention_type='user',
    )
    events = storage.list_events(seed_channel)
    ev = next(e for e in events if e['id'] == eid)
    assert ev['mention_type'] == 'user'
    assert ev['target_user_id'] == '1234567890'
