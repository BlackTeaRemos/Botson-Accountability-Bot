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
    type: str  # Event name identifier
    payload: Dict[str, Any]  # Serializable event data
    context: Dict[str, Any] = field(default_factory=lambda: cast(Dict[str, Any], {}))  # Metadata for tracing
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # UTC creation time
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)  # Unique tracing ID

Handler = Callable[[Event], Coroutine[Any, Any, None]]  # Type alias for event handler functions

class EventBus:
    """Simple async event bus.

    Handlers are awaited sequentially; if one raises it propagates upward.
    Wildcard handlers receive all events (used for logging/introspection).
    """
    def __init__(self):
        self._handlers: Dict[str, List[Handler]] = {}  # Handlers for specific event types
        self._wildcard: List[Handler] = []  # Wildcard handlers for all events

    def Subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a handler for a specific event type.

        Args:
            event_type: The event type to listen for.
            handler: The async function to call when the event is published.

        Returns:
            None

        Example:
            async def my_handler(event):
                print(f"Received {event.type}")

            bus.Subscribe("MessageReceived", my_handler)
        """
        self._handlers.setdefault(event_type, []).append(handler)

    def SubscribeAll(self, handler: Handler) -> None:
        """Register a wildcard handler that sees every event.

        Args:
            handler: The async function to call for all events.

        Returns:
            None

        Example:
            async def log_handler(event):
                print(f"Event: {event.type}")

            bus.SubscribeAll(log_handler)
        """
        self._wildcard.append(handler)

    async def Publish(self, event: Event) -> None:
        """Publish a pre-built Event to matching handlers.

        Args:
            event: The event instance to publish.

        Returns:
            None

        Example:
            event = Event(type="Test", payload={})
            await bus.Publish(event)
        """
        try:
            for h in list(self._handlers.get(event.type, [])):
                await h(event)
            for h in list(self._wildcard):
                await h(event)
        except Exception as e:
            raise RuntimeError(f"Failed to publish event {event.type}: {e}") from e

    async def Emit(self, type: str, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Event:
        """Create and publish an Event in one call.

        Args:
            type: The event type name.
            payload: The event data dictionary.
            context: Optional metadata dictionary.

        Returns:
            Event: The created event instance for tracing/testing.

        Example:
            event = await bus.Emit("UserAction", {"action": "click"})
        """
        try:
            ev = Event(type=type, payload=payload, context=context or {})
            await self.Publish(ev)
            return ev
        except Exception as e:
            raise RuntimeError(f"Failed to emit event {type}: {e}") from e
