"""Schedule expression utilities.

Provides:
- parse_schedule_expr: parse strings like "d2h4m30" into a dict
- build_schedule_expr: build an expression string from parts
- compute_next_run_from_anchor: compute the next run time from an anchor (week, month, year) with minute precision

Expression grammar:
  sequence of tokens: w<num> d<num> h<num> m<num>
  where:
    w = weeks, d = days, h = hours, m = minutes (all non-negative integers)
  example: "d2h4" => every 2 days and 4 hours

Anchors:
  - week: aligned to Monday 00:00 of the current or next week (ISO week)
  - month: aligned to the 1st day of the month at 00:00
  - year: aligned to Jan 1st 00:00

All datetimes are timezone-aware (UTC).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple


@dataclass(frozen=True)
class ScheduleInterval:
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0

    def to_timedelta(self) -> timedelta:
        return timedelta(weeks=self.weeks, days=self.days, hours=self.hours, minutes=self.minutes)

    def is_zero(self) -> bool:
        return self.weeks == 0 and self.days == 0 and self.hours == 0 and self.minutes == 0


def parse_schedule_expr(expr: str) -> ScheduleInterval:
    """Parse a schedule expression like "d2h4m30" into a ScheduleInterval.

    Args:
        expr: String expression using tokens w,d,h,m with integer values.

    Returns:
        ScheduleInterval with the parsed values (missing tokens default to 0).

    Raises:
        ValueError: If the expression contains invalid tokens or negative numbers.
    """
    expr = (expr or "").strip().lower()
    if not expr:
        return ScheduleInterval()
    i = 0
    values: Dict[str, int] = {"w": 0, "d": 0, "h": 0, "m": 0}
    valid = set(values.keys())
    while i < len(expr):
        token = expr[i]
        if token not in valid:
            raise ValueError(f"Invalid token '{token}' in expression '{expr}'")
        i += 1
        # read number
        start = i
        while i < len(expr) and expr[i].isdigit():
            i += 1
        if start == i:
            raise ValueError(f"Missing number after '{token}' in '{expr}'")
        num = int(expr[start:i])
        if num < 0:
            raise ValueError("Negative values are not allowed")
        values[token] = values[token] + num
    return ScheduleInterval(weeks=values["w"], days=values["d"], hours=values["h"], minutes=values["m"])


def build_schedule_expr(weeks: int = 0, days: int = 0, hours: int = 0, minutes: int = 0) -> str:
    """Build a compact expression string from components.

    Tokens appear in w,d,h,m order and are omitted if zero.
    """
    parts: list[str] = []
    if weeks:
        parts.append(f"w{int(weeks)}")
    if days:
        parts.append(f"d{int(days)}")
    if hours:
        parts.append(f"h{int(hours)}")
    if minutes:
        parts.append(f"m{int(minutes)}")
    return "".join(parts) or "m0"


def _compute_anchor(now: datetime, anchor: str) -> datetime:
    tz = timezone.utc
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    anchor_l = anchor.lower().strip()
    if anchor_l == "week":
        # Monday 00:00 of current week
        monday = now - timedelta(days=now.weekday())
        return datetime(monday.year, monday.month, monday.day, 0, 0, tzinfo=tz)
    if anchor_l == "month":
        return datetime(now.year, now.month, 1, 0, 0, tzinfo=tz)
    if anchor_l == "year":
        return datetime(now.year, 1, 1, 0, 0, tzinfo=tz)
    raise ValueError(f"Unsupported anchor '{anchor}' (expected: week, month, year)")


def compute_next_run_from_anchor(anchor: str, expr: str, *, now: datetime | None = None) -> Tuple[datetime, ScheduleInterval]:
    """Compute the next run datetime from a synchronized anchor and interval expression.

    The returned datetime is UTC and aligned to the anchor plus N*interval with minute precision
    (seconds and microseconds set to zero).

    Rules:
    - If the interval is zero, raise ValueError.
    - We compute the minimal k >= 1 such that anchor+ k*interval > now.
    - If now is before the first interval step (k=1), return anchor+interval.
    - Return the computed datetime with seconds/microseconds zeroed.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    # drop seconds/micros for precision guarantee
    now = now.replace(second=0, microsecond=0)
    interval = parse_schedule_expr(expr)
    if interval.is_zero():
        raise ValueError("Interval must be non-zero")
    anchor_dt = _compute_anchor(now, anchor)
    step = interval.to_timedelta()

    # Compute k such that anchor + k*step > now
    # Start with k=1
    candidate = anchor_dt + step
    if candidate > now:
        return candidate, interval
    # Estimate k using floor division on total seconds to avoid looping when large
    elapsed = (now - anchor_dt).total_seconds()
    step_s = max(60.0, step.total_seconds())  # at least minute precision
    k_est = int(elapsed // step_s) + 1
    candidate = anchor_dt + k_est * step
    if candidate > now:
        return candidate, interval
    # Fallback increment to handle edge off-by-one
    return candidate + step, interval
