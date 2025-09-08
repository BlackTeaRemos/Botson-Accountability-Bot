from __future__ import annotations

import base64
from typing import Any

import pytest  # type: ignore

from src.services.persistence import PersistenceService
from src.services.event_scheduler import EventScheduler


def _make_reminder_command(msg: str) -> str:
    payload = base64.urlsafe_b64encode(msg.encode("utf-8")).decode("ascii")
    return "reminder:" + payload


class _FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str, **_: Any) -> None:  # ignore extra kwargs like file/embeds
        self.sent.append(content)


class _FakeBot:
    def __init__(self, ch: _FakeChannel) -> None:
        self._ch = ch

    def get_channel(self, _cid: int) -> _FakeChannel:
        return self._ch

    async def fetch_channel(self, _cid: int) -> _FakeChannel:
        return self._ch


def test_persistence_adds_reminder_event(storage: PersistenceService, seed_channel: int) -> None:
    cmd = _make_reminder_command("Drink water")
    eid = storage.add_event(
        channel_discord_id=seed_channel,
        interval_minutes=0,
        command=cmd,
        schedule_anchor="week",
        schedule_expr="h1",
    )
    assert isinstance(eid, int)
    events = storage.list_events(channel_discord_id=seed_channel)
    assert any(ev["id"] == eid and isinstance(ev["command"], str) and ev["command"].startswith("reminder:") for ev in events)


@pytest.mark.asyncio  # type: ignore
async def test_scheduler_executes_reminder(storage: PersistenceService, seed_channel: int) -> None:
    # Insert an event and force it due now
    cmd = _make_reminder_command("Stand up and stretch")
    eid = storage.add_event(
        channel_discord_id=seed_channel,
        interval_minutes=0,
        command=cmd,
        schedule_anchor="week",
        schedule_expr="m1",
    )
    # Mark due by setting next_run in the past
    session = storage.db.GetSession()
    try:
        from src.db.models import ScheduledEvent
        ev = session.get(ScheduledEvent, eid)
        assert ev is not None
        import datetime as _dt
        from datetime import timezone as _tz
        # Use setattr to satisfy SQLAlchemy typing and set aware UTC time in the past
        setattr(ev, "next_run", _dt.datetime.now(tz=_tz.utc) - _dt.timedelta(seconds=1))
        session.commit()
    finally:
        session.close()

    ch = _FakeChannel()
    bot = _FakeBot(ch)
    sched = EventScheduler(bot, storage)
    # Execute due events once
    # Call once to process due events (protected in implementation; acceptable in tests)
    await sched._check_and_run()  # type: ignore[attr-defined]
    # Expect the decoded text to be sent once
    assert any("Stand up and stretch" in s for s in ch.sent)
