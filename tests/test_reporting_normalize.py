from __future__ import annotations

from typing import Any, Dict, List
from src.core.config import AppConfig
from src.db.connection import Database
from src.services.reporting import ReportingService


def _service(db: Database, daily_goal: int = 5) -> ReportingService:
    return ReportingService(db, AppConfig(discord_token="", database_path="", daily_goal_tasks=daily_goal))


def test_normalize_repairs_dates_and_clamps_negative(db: Database) -> None:
    svc = _service(db)
    rows: List[Dict[str, Any]] = [
        {"user_id": "1", "date": "2024/01/02", "raw_score_sum": "1.0"},  # repair /
        {"user_id": "2", "date": "02-01-2024", "raw_score_sum": 0.6},     # repair d-m-Y
        {"user_id": "3", "date": "20240103", "raw_score_sum": -0.2},       # clamp negative
        {"user_id": "4", "date": "bad", "raw_score_sum": 0.3},             # drop
        {"user_id": "5", "date": 20240104, "raw_score_sum": 0.3},           # non-str date -> drop
        {"user_id": "1", "date": "2024-01-02", "raw_score_sum": 0.25},     # duplicate date sums
    ]
    normalized, warnings = getattr(svc, "_normalize")(rows)
    # 'bad' and non-string dates dropped; repaired ones should appear
    assert "1" in normalized and "2" in normalized and "3" in normalized
    assert "2024-01-02" in normalized["1"]
    # user 1: 1.0 + 0.25 -> capped to daily_goal (5) scaling to 5 when divided by 5 -> 1.25/5*5=1.25, rounded 2 decimals
    # But normalization scales min(score, daily_goal)/daily_goal*5
    # Score for date 2024-01-02 is 1.25 -> 1.25/5*5 = 1.25
    assert abs(normalized["1"]["2024-01-02"] - 1.25) < 1e-9
    # Negative was clamped to 0.0 and then scaled -> 0.0
    assert normalized["3"].values() and next(iter(normalized["3"].values())) == 0.0
    # Warnings mention repairs and drops
    assert any("Repaired date" in w or "Dropped row" in w for w in warnings)


def test_normalize_caps_to_daily_goal_and_rounds(db: Database) -> None:
    svc = _service(db, daily_goal=2)  # small goal to trigger cap
    rows: List[Dict[str, Any]] = [
        {"user_id": "u", "date": "2024-01-01", "raw_score_sum": 3.7},
    ]
    normalized, warnings = getattr(svc, "_normalize")(rows)
    assert warnings == []
    # min(3.7, 2)/2 * 5 = 5 -> full score
    assert normalized["u"]["2024-01-01"] == 5.0
