from __future__ import annotations

from datetime import datetime, timezone

from src.core.events import EventBus
from src.services.habit_parser import HabitParser


def test_habit_parser_extracts_date_and_brackets() -> None:
    hp = HabitParser(EventBus())
    ts = datetime(2025, 1, 2, tzinfo=timezone.utc)
    result = hp.parse_message("Did stuff [x] and [ ] on Jan 2", ts)
    assert result is not None
    assert result["extracted_date"] == "2025-01-02"
    assert result["raw_bracket_count"] == 2
    assert result["filled_bracket_count"] == 1
    assert 0.0 < result["confidence"] <= 1.0


def test_habit_parser_handles_no_brackets() -> None:
    hp = HabitParser(EventBus())
    ts = datetime.now(timezone.utc)
    assert hp.parse_message("No brackets here", ts) is None


def test_habit_parser_confidence_scales_with_count() -> None:
    hp = HabitParser(EventBus())
    ts = datetime(2025, 1, 2, tzinfo=timezone.utc)
    many = hp.parse_message(" ".join(["[x]"] * 10) + " Jan 2", ts)
    few = hp.parse_message("[x] Jan 2", ts)
    assert many is not None and few is not None
    assert many["confidence"] >= few["confidence"]


def test_parse_message_with_date_and_brackets() -> None:
    bus = EventBus()
    parser = HabitParser(bus)
    # Content with 3 brackets, two filled, includes month name with ordinal suffix
    content = "I did things [x] [ ] [done] on Jan 2nd"
    msg_ts = datetime(2024, 1, 3, 12, 0, 0, tzinfo=timezone.utc)
    parsed = parser.parse_message(content, msg_ts)
    assert parsed is not None
    assert parsed["extracted_date"] == "2024-01-02"
    assert parsed["raw_bracket_count"] == 3
    assert parsed["filled_bracket_count"] == 2
    assert abs(parsed["raw_ratio"] - (2 / 3)) < 1e-9
    # Confidence includes 0.5 for having a date + 3/20 up to 0.5
    assert 0.5 <= parsed["confidence"] <= 1.0


def test_parse_message_without_date() -> None:
    bus = EventBus()
    parser = HabitParser(bus)
    content = "[] [] []"
    msg_ts = datetime(2024, 1, 3, 12, 0, 0, tzinfo=timezone.utc)
    parsed = parser.parse_message(content, msg_ts)
    assert parsed is not None
    assert parsed["extracted_date"] is None
    assert parsed["raw_bracket_count"] == 3
    assert parsed["filled_bracket_count"] == 0
    assert parsed["raw_ratio"] == 0.0


def test_parse_message_without_brackets_returns_none() -> None:
    bus = EventBus()
    parser = HabitParser(bus)
    assert parser.parse_message("no brackets here", datetime(2024, 1, 3, tzinfo=timezone.utc)) is None
