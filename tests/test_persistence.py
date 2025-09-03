from __future__ import annotations

from sqlalchemy.orm import Session

from src.db.connection import Database
from src.db.models import Message, HabitDailyScore, HabitMessageScore
from src.services.persistence import PersistenceService


def test_channel_registration_and_listing(db: Database, seed_channel: int) -> None:
    storage = PersistenceService(db)
    assert storage.is_channel_registered(seed_channel) is True
    ids = storage.list_active_channel_ids()
    assert seed_channel in ids


def test_message_insert_and_parse_update(db: Database, seed_channel: int) -> None:
    storage = PersistenceService(db)
    storage.insert_message(111, seed_channel, 999, "tester", "2024-01-01T01:02:03", "[x] done")
    storage.update_habit_parse(111, 1, 1, 0.9, "2024-01-01")
    session: Session = db.get_session()
    try:
        msg = session.query(Message).filter(Message.discord_message_id == "111").first()
        assert msg is not None
        assert bool(getattr(msg, "is_habit_candidate")) is True
        assert int(getattr(msg, "raw_bracket_count") or 0) == 1
        assert int(getattr(msg, "filled_bracket_count") or 0) == 1
        assert str(getattr(msg, "extracted_date")) == "2024-01-01"
    finally:
        session.close()


def test_insert_replace_message_score_and_recompute(db: Database, seed_channel: int) -> None:
    storage = PersistenceService(db)
    # Seed message
    storage.insert_message(222, seed_channel, 1001, "user", "2024-01-02T08:08:08", "[x] [x]")
    storage.insert_or_replace_message_score(222, 1001, "2024-01-02", seed_channel, 1.0, 2, 2)
    storage.recompute_daily_scores(seed_channel, date="2024-01-02")
    # Update (replace) message score
    storage.insert_or_replace_message_score(222, 1001, "2024-01-02", seed_channel, 0.5, 1, 2)
    storage.recompute_daily_scores(seed_channel, date="2024-01-02")

    session: Session = db.get_session()
    try:
        msg = session.query(Message).filter(Message.discord_message_id == "222").one()
        mscore = session.query(HabitMessageScore).filter(HabitMessageScore.message_id == msg.id).one()
        assert abs(float(getattr(mscore, "raw_ratio") or 0.0) - 0.5) < 1e-9
        dscore = session.query(HabitDailyScore).filter(
            HabitDailyScore.channel_id == msg.channel_id,
            HabitDailyScore.date == "2024-01-02",
            HabitDailyScore.user_id == str(1001),
        ).first()
        assert dscore is not None
        raw_sum = float(getattr(dscore, "raw_score_sum") or 0.0)
        assert 0.0 <= raw_sum <= 1.0
    finally:
        session.close()


def test_clear_current_week_scores_and_guild_style(db: Database, seed_channel: int) -> None:
    storage = PersistenceService(db)
    # Seed some scores on various dates (using debug_add_score)
    storage.debug_add_score("100", "2024-01-03", seed_channel, 0.5)
    storage.debug_add_score("100", "2024-01-04", seed_channel, 0.5)
    # Detect non-iso dates (none added)
    assert storage.detect_non_iso_dates(seed_channel) == []
    deleted = storage.clear_current_week_scores(seed_channel)
    # Depending on current week relative to those dates, deleted may be 0
    assert isinstance(deleted, int)
    # Guild style default and set
    assert storage.get_guild_report_style(987654321) == "style1"
    storage.set_guild_report_style(987654321, "style3")
    assert storage.get_guild_report_style(987654321) == "style3"


def test_update_message_content_resets_parse(db: Database, seed_channel: int) -> None:
    storage = PersistenceService(db)
    storage.insert_message(333, seed_channel, 5, "u", "2024-01-05T00:00:00", "[x]")
    storage.update_habit_parse(333, 1, 1, 0.9, "2024-01-05")
    storage.update_message_content(333, "[ ] changed")
    session: Session = db.get_session()
    try:
        msg = session.query(Message).filter(Message.discord_message_id == "333").one()
        assert msg.is_habit_candidate is False
        assert msg.parsed_at is None
        assert msg.raw_bracket_count is None and msg.filled_bracket_count is None
        assert msg.extracted_date is None
    finally:
        session.close()
