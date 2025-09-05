from __future__ import annotations

from pathlib import Path
from sqlalchemy.orm import Session

from src.db.connection import Database
from src.db.models import Channel, Message, HabitMessageScore, HabitDailyScore
from src.services.diagnostics import DiagnosticsService
from src.services.persistence import PersistenceService


def test_migrations_create_db_and_tables(db: Database) -> None:
    # Smoke-check that a basic query works and tables exist
    session: Session = db.GetSession()
    try:
        session.query(Channel).first()
        session.query(Message).first()
    finally:
        session.close()


def test_inserts_and_commits(db: Database) -> None:
    # Insert a channel and a message and ensure counts increase
    session: Session = db.GetSession()
    try:
        if not session.query(Channel).filter(Channel.discord_channel_id == "12345").first():
            session.add(Channel(discord_channel_id="12345", registered_by="tester", active=True))
            session.commit()
    finally:
        session.close()

    storage = PersistenceService(db)

    # Insert a message and parse/update scores
    storage.insert_message(
        discord_message_id=111,
        channel_id=12345,
        author_id=999,
        author_display="tester",
        created_at="2024-01-01T12:34:56",
        content="[x] did a thing",
    )

    storage.update_habit_parse(
        discord_message_id=111,
        raw_bracket_count=1,
        filled_bracket_count=1,
        confidence=0.9,
        extracted_date="2024-01-01",
    )

    storage.insert_or_replace_message_score(
        discord_message_id=111,
        user_id=999,
        date="2024-01-01",
        channel_discord_id=12345,
        raw_ratio=1.0,
        filled=1,
        total=1,
    )

    storage.recompute_daily_scores(channel_discord_id=12345, date="2024-01-01")

    session = db.GetSession()
    try:
        msg = session.query(Message).filter(Message.discord_message_id == "111").first()
        assert msg is not None
        score = session.query(HabitMessageScore).filter(HabitMessageScore.message_id == msg.id).first()
        assert score is not None
        daily = (
            session.query(HabitDailyScore)
            .filter(
                HabitDailyScore.channel_id == msg.channel_id,
                HabitDailyScore.user_id == str(999),
                HabitDailyScore.date == "2024-01-01",
            )
            .first()
        )
        assert daily is not None
    finally:
        session.close()


def test_diagnostics_reports_ok(db: Database) -> None:
    from typing import Dict, Any
    from src.core.events import Event, EventBus

    class DummyBus(EventBus):
        async def emit(self, type: str, payload: Dict[str, Any], context: Dict[str, Any] | None = None) -> Event:
            # Create and return an Event instance (no-op publish)
            return Event(type=type, payload=payload, context=context or {})

    diag = DiagnosticsService(bus=DummyBus(), db=db, db_path=":memory:")
    snapshot = diag.collect()
    assert snapshot.get("database", {}).get("status") == "ok"
    assert "counts" in snapshot


def test_migration_creates_db_when_dir_missing(tmp_path: Path) -> None:
    import os
    from src.db.connection import Database
    from src.db.migrations import EnsureMigrated

    nested = tmp_path / "nested" / "deep"
    db_path = nested / "created.db"
    EnsureMigrated(str(db_path))
    assert os.path.exists(db_path), "Database file should be created by EnsureMigrated()"

    # Idempotency: calling again should not raise and schema_version should have at least one row
    EnsureMigrated(str(db_path))

    database = Database(str(db_path))
    session = database.GetSession()
    try:
        rows = session.execute(__import__("sqlalchemy").text("SELECT COUNT(1) FROM schema_version")).scalar_one()
        assert rows >= 1
    finally:
        session.close()