from __future__ import annotations
"""Lightweight asynchronous in-process event bus.

Provides an `Event` data structure and an `EventBus` with subscribe/emit semantics.
Used to decouple Discord gateway events from domain logic and allow future
instrumentation (logging, metrics) via wildcard subscribers.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, cast
import uuid

@dataclass(slots=True)
class Event:
    """Represents a domain event published on the internal bus.

    Attributes:
        type: Event name (e.g. "MessageReceived").
        payload: Event data dictionary (serializable fields preferred).
        context: Out-of-band metadata (trace IDs, user info, etc.).
        timestamp: UTC creation time.
        correlation_id: Unique id for tracing event flow.
    """
    type: str
    payload: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=lambda: cast(Dict[str, Any], {}))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)

Handler = Callable[[Event], Coroutine[Any, Any, None]]

class EventBus:
    """Simple async event bus.

    Handlers are awaited sequentially; if one raises it propagates upward.
    Wildcard handlers receive all events (used for logging/introspection).
    """
    def __init__(self):
        self._handlers: Dict[str, List[Handler]] = {}
        self._wildcard: List[Handler] = []

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a handler for a specific event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: Handler) -> None:
        """Register a wildcard handler that sees every event."""
        self._wildcard.append(handler)

    async def publish(self, event: Event) -> None:
        """Publish a pre-built Event to matching handlers."""
        for h in list(self._handlers.get(event.type, [])):
            await h(event)
        for h in list(self._wildcard):
            await h(event)

    async def emit(self, type: str, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Event:
        """Create and publish an Event in one call.

        Returns the created Event instance for tracing/testing.
        """
        ev = Event(type=type, payload=payload, context=context or {})
        await self.publish(ev)
        return ev
