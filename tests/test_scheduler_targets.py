from typing import Any, List, cast

from src.services.scheduler import ReportScheduler


class _DummyStorage:
    def __init__(self, ids: List[int]) -> None:
        self._ids: List[int] = list(ids)
        self.calls: int = 0  # number of times list_active_channel_ids called

    def list_active_channel_ids(self) -> List[int]:
        self.calls += 1
        return list(self._ids)


class _DummyReporting:
    pass


class _DummyBot:
    pass


class _DummyConfig:
    def __init__(self, ids: List[int], interval_minutes: int = 60) -> None:
        # Explicit configured channel IDs for scheduler
        self.scheduled_report_channel_ids: List[int] = list(ids)
        # Interval required by scheduler loop, not used in these tests
        self.scheduled_report_interval_minutes: int = interval_minutes


class _ExposedReportScheduler(ReportScheduler):
    """Subclass exposing the protected target selection for testing."""

    def target_channel_ids(self) -> List[int]:
        return super()._target_channel_ids()


def test_target_channels_prefers_configured_list():
    storage = _DummyStorage(ids=[1, 2, 3])
    cfg = _DummyConfig(ids=[42, 43])
    scheduler = _ExposedReportScheduler(
        bot=cast(Any, _DummyBot()),
        storage=cast(Any, storage),
        reporting=cast(Any, _DummyReporting()),
        config=cast(Any, cfg),
    )

    result = scheduler.target_channel_ids()

    assert result == [42, 43]
    # Should not fall back to storage when config list is non-empty
    assert storage.calls == 0


def test_target_channels_fallbacks_to_active_channels_when_unset_or_empty():
    storage = _DummyStorage(ids=[10, 11])
    # Empty list should trigger fallback
    cfg_empty = _DummyConfig(ids=[])
    scheduler_empty = _ExposedReportScheduler(
        bot=cast(Any, _DummyBot()),
        storage=cast(Any, storage),
        reporting=cast(Any, _DummyReporting()),
        config=cast(Any, cfg_empty),
    )
    result_empty = scheduler_empty.target_channel_ids()
    assert result_empty == [10, 11]
    assert storage.calls == 1

    # None-like behavior: when attribute is falsy, fallback applies
    storage2 = _DummyStorage(ids=[99])
    cfg_none_like = _DummyConfig(ids=[])
    # Explicitly set to empty to keep semantics clear; scheduler checks truthiness
    scheduler_none_like = _ExposedReportScheduler(
        bot=cast(Any, _DummyBot()),
        storage=cast(Any, storage2),
        reporting=cast(Any, _DummyReporting()),
        config=cast(Any, cfg_none_like),
    )
    result_none_like = scheduler_none_like.target_channel_ids()
    assert result_none_like == [99]
    assert storage2.calls == 1
