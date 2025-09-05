from __future__ import annotations

from typing import List
from datetime import datetime, timezone
import pytest  # type: ignore

from src.core.events import EventBus, Event


async def _collect(events: List[str], prefix: str, ev: Event) -> None:
    events.append(f"{prefix}:{ev.type}")


@pytest.mark.asyncio  # type: ignore
async def test_event_bus_subscribe_and_emit_order() -> None:
    bus = EventBus()
    calls: List[str] = []

    async def h1(ev: Event):
        await _collect(calls, "h1", ev)

    async def h2(ev: Event):
        await _collect(calls, "h2", ev)

    bus.Subscribe("A", h1)
    bus.Subscribe("A", h2)
    ev = await bus.Emit("A", {"x": 1}, {})

    assert ev.type == "A"
    assert ev.payload == {"x": 1}
    assert len(calls) == 2 and calls[0] == "h1:A" and calls[1] == "h2:A"
    assert ev.correlation_id and len(ev.correlation_id) >= 8
    assert abs((ev.timestamp - datetime.now(timezone.utc)).total_seconds()) < 5


@pytest.mark.asyncio  # type: ignore
async def test_event_bus_wildcard_and_propagation() -> None:
    bus = EventBus()
    calls: List[str] = []

    async def raising(ev: Event):
        raise RuntimeError("boom")

    async def wildcard(ev: Event):
        await _collect(calls, "wild", ev)

    bus.Subscribe("A", raising)
    bus.SubscribeAll(wildcard)

    with pytest.raises(RuntimeError):  # type: ignore
        await bus.Emit("A", {}, {})

    # Raising handler stops before wildcard execution
    assert calls == []
