from datetime import datetime, timezone, timedelta

from src.services.schedule_expression import (
    parse_schedule_expr,
    build_schedule_expr,
    compute_next_run_from_anchor,
)


def test_parse_and_build_roundtrip():
    s = "d2h4m30"
    interval = parse_schedule_expr(s)
    assert interval.days == 2
    assert interval.hours == 4
    assert interval.minutes == 30
    assert build_schedule_expr(interval.weeks, interval.days, interval.hours, interval.minutes) == s


def test_compute_next_run_week_anchor_simple():
    # Fixed now at Monday 00:00 UTC, interval 2 days 4 hours
    now = datetime(2025, 9, 1, 0, 0, tzinfo=timezone.utc)  # Monday
    next_run, interval = compute_next_run_from_anchor("week", "d2h4", now=now)
    assert next_run == datetime(2025, 9, 3, 4, 0, tzinfo=timezone.utc)


def test_compute_next_run_week_anchor_progressed():
    # If now is after the first candidate, we should advance to the next multiple
    now = datetime(2025, 9, 4, 5, 0, tzinfo=timezone.utc)  # Thursday 05:00
    next_run, _ = compute_next_run_from_anchor("week", "d2h4", now=now)
    # Monday 00:00 + 2d4h = Wed 04:00, +2d4h = Fri 08:00 -> next after now
    assert next_run == datetime(2025, 9, 5, 8, 0, tzinfo=timezone.utc)


def test_month_anchor_minutes_only():
    now = datetime(2025, 9, 15, 12, 34, tzinfo=timezone.utc)
    next_run, _ = compute_next_run_from_anchor("month", "m30", now=now)
    # Anchor is 2025-09-01 00:00, 30-minute steps -> compute
    assert next_run > now
    assert next_run.second == 0 and next_run.microsecond == 0
