from __future__ import annotations

from typing import Any
from src.db.connection import Database
from src.db.models import Channel, HabitDailyScore
from src.services.reporting import ReportingService
from src.core.dynaconf_settings import AppConfig
from src.db.migrations import EnsureMigrated


def _make_config() -> AppConfig:
    # Minimal viable AppConfig-like object
    return AppConfig(
        discord_token="dummy",
        database_path=":memory:",
        timezone="UTC",
        use_db_only=False,
        backfill_default_days=7,
        guild_id=None,
        daily_goal_tasks=5,
        scheduled_reports_enabled=False,
        scheduled_report_interval_minutes=60,
        scheduled_report_channel_ids=tuple(),
    )


def test_get_weekly_structured_handles_bad_rows(tmp_path):
    db = Database(str(tmp_path / "struct.sqlite"))
    # ensure tables exist
    EnsureMigrated(str(tmp_path / "struct.sqlite"))
    cfg = _make_config()
    reporting = ReportingService(db, cfg)

    # Seed minimal data with one good and two malformed rows
    session = db.GetSession()
    try:
        # channel
        ch = Channel(discord_channel_id="1", registered_by="t", active=True)
        session.add(ch)
        session.commit()
        # good row
        session.add(HabitDailyScore(user_id="u1", date="2024-01-02", channel_id=ch.id, raw_score_sum=1.0, normalized_score=0.0, messages_count=1))
        # malformed date
        session.add(HabitDailyScore(user_id="u1", date="20240102", channel_id=ch.id, raw_score_sum=0.5, normalized_score=0.0, messages_count=1))
        # negative raw sum
        session.add(HabitDailyScore(user_id="u2", date="2024-01-03", channel_id=ch.id, raw_score_sum=-2.0, normalized_score=0.0, messages_count=1))
        session.commit()
    finally:
        session.close()

    dates, per_user, totals, warnings = reporting.get_weekly_structured(days=7)
    # Dates should only include ISO date from the good/mended ones
    assert "2024-01-02" in dates
    # Negative values are clamped to 0 inside normalization
    # per_user entries contain floats keyed by dates and 'total'
    for user in per_user:
        for d in dates:
            assert isinstance(user.get(d, 0.0), (int, float))
    # Warnings should be present for malformed/negative
    assert warnings
