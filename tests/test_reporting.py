from __future__ import annotations

from io import BytesIO

from src.core.config import AppConfig
from src.db.connection import Database
from src.services.persistence import PersistenceService
from src.services.reporting import ReportingService


def seed_scores(storage: PersistenceService, channel_id: int) -> None:
    # Two users across three days; ensure recompute generates daily rows
    storage.insert_message(1001, channel_id, 1, "u1", "2024-01-01T00:00:00", "[x]")
    storage.insert_or_replace_message_score(1001, 1, "2024-01-01", channel_id, 1.0, 1, 1)
    storage.insert_message(1002, channel_id, 2, "u2", "2024-01-01T00:00:00", "[ ] [x]")
    storage.insert_or_replace_message_score(1002, 2, "2024-01-01", channel_id, 0.5, 1, 2)
    storage.insert_message(1003, channel_id, 1, "u1", "2024-01-02T00:00:00", "[x] [x]")
    storage.insert_or_replace_message_score(1003, 1, "2024-01-02", channel_id, 1.0, 2, 2)
    storage.insert_message(1004, channel_id, 2, "u2", "2024-01-03T00:00:00", "[ ] [ ]")
    storage.insert_or_replace_message_score(1004, 2, "2024-01-03", channel_id, 0.0, 0, 2)
    storage.recompute_daily_scores(channel_id)


def test_reporting_structured_and_image(db: Database, seed_channel: int) -> None:
    storage = PersistenceService(db)
    seed_scores(storage, seed_channel)
    config = AppConfig(discord_token="", database_path="", daily_goal_tasks=5)
    reporting = ReportingService(db, config)
    # Structured
    dates, per_user, _totals, _warnings = reporting.get_weekly_structured(days=30)
    assert len(dates) >= 3
    assert any(u["user_id"] == "1" for u in per_user)
    assert any(u["user_id"] == "2" for u in per_user)
    assert set(dates).issuperset({"2024-01-01", "2024-01-02", "2024-01-03"})
    # Image
    buf, human_dates, _warns = reporting.generate_weekly_table_image(days=30, style="style2")
    assert isinstance(buf, BytesIO)
    content = buf.getvalue()
    assert len(content) > 1000  # some PNG bytes
    assert len(human_dates) >= 3