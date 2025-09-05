import re
from typing import Optional, Any, Dict
from datetime import datetime
from ..core.events import EventBus

DATE_REGEX = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE
)
BRACKET_REGEX = re.compile(r"\[(.*?)\]")

class HabitParser:
    """Parses messages for habit-tracking bracket items and optional dates.

    This class stores an EventBus instance and provides ParseMessage to analyze
    a message's text for bracketed entries and a date.

    Attributes:
        bus: EventBus instance for emitting events.
    """

    def __init__(self, bus: EventBus) -> None:
        """Initialize the HabitParser.

        Args:
            bus: EventBus instance for event handling.
        """
        self.bus = bus

    def ParseMessage(self, content: str, message_ts: datetime) -> Optional[Dict[str, Any]]:
        """Parse a message for habit brackets and date.

        Args:
            content: Plain text containing bracketed items like "[x]" or "[]".
            message_ts: Datetime of the message, used for year when parsing dates.

        Returns:
            Dict with parsed data if successful, None otherwise.
                Keys: extracted_date (Optional[str]), raw_bracket_count (int),
                filled_bracket_count (int), raw_ratio (float), confidence (float).

        Raises:
            No exceptions raised; returns None on failure.
        """
        if '[' not in content or ']' not in content:
            return None
        date_match_result = DATE_REGEX.search(content)
        extracted_date = None
        if date_match_result:
            month = date_match_result.group(1)[:3].title()
            day = date_match_result.group(2)
            try:
                parsed_datetime = datetime.strptime(
                    f"{month} {day} {message_ts.year}",
                    "%b %d %Y"
                )
                extracted_date = parsed_datetime.strftime('%Y-%m-%d')
            except ValueError:
                pass
        found_brackets = BRACKET_REGEX.findall(content)
        if not found_brackets:
            return None
        total_bracket_count = len(found_brackets)
        filled_bracket_count = sum(
            1 for bracket in found_brackets if bracket.strip()
        )
        completion_ratio = (
            filled_bracket_count / total_bracket_count
            if total_bracket_count else 0.0
        )
        parsing_confidence = 0.0
        if extracted_date:
            parsing_confidence += 0.5
        parsing_confidence += min(0.5, total_bracket_count / 20.0)
        return {
            "extracted_date": extracted_date,
            "raw_bracket_count": total_bracket_count,
            "filled_bracket_count": filled_bracket_count,
            "raw_ratio": completion_ratio,
            "confidence": round(parsing_confidence, 3),
        }
