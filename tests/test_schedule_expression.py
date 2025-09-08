from datetime import datetime, timezone

from src.services.schedule_expression import (
    parse_schedule_expr,
    build_schedule_expr,
    compute_next_run_from_anchor,
    compute_next_run_from_anchor_with_offset,
    compute_next_run_from_week_expr,
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
    next_run, _ = compute_next_run_from_anchor("week", "d2h4", now=now)
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


def test_week_expr_with_offset_basic():
    # Monday 00:00, weekly, offset Wednesday 10:00 (d2h10)
    now = datetime(2025, 9, 1, 0, 0, tzinfo=timezone.utc)  # Monday
    next_run, interval = compute_next_run_from_week_expr("w1@d2h10", now=now)
    assert interval.weeks == 1
    assert next_run == datetime(2025, 9, 3, 10, 0, tzinfo=timezone.utc)


def test_week_expr_with_offset_progressed_into_next_week():
    # If now has passed this week's offset, result should be next week's offset
    now = datetime(2025, 9, 4, 12, 0, tzinfo=timezone.utc)  # Thursday noon
    next_run, _ = compute_next_run_from_week_expr("w1@d2h10", now=now)
    # Next week's Monday is 2025-09-08, +2d10h = 2025-09-10 10:00
    assert next_run == datetime(2025, 9, 10, 10, 0, tzinfo=timezone.utc)


def test_anchor_with_offset_two_weeks_every_other_wednesday():
    # Every 2 weeks, Wednesday 09:30
    now = datetime(2025, 9, 1, 0, 0, tzinfo=timezone.utc)  # Monday
    next_run, interval = compute_next_run_from_anchor_with_offset("week", "w2", "d2h9m30", now=now)
    assert interval.weeks == 2
    assert next_run == datetime(2025, 9, 3, 9, 30, tzinfo=timezone.utc)


def test_anchor_with_offset_month_anchor_literal_offset():
    # Month anchor with offset 2d10h, steps of 1 week
    now = datetime(2025, 9, 15, 0, 0, tzinfo=timezone.utc)
    # Anchor 2025-09-01 00:00 + 2d10h -> 2025-09-03 10:00, then every 1w steps
    next_run, _ = compute_next_run_from_anchor_with_offset("month", "w1", "d2h10", now=now)
    # After 2025-09-15, the next occurrences from 2025-09-03 10:00 every 7 days are
    # 09-10 10:00, 09-17 10:00 -> we expect 09-17 10:00
    assert next_run == datetime(2025, 9, 17, 10, 0, tzinfo=timezone.utc)
