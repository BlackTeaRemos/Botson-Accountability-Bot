"""Service to schedule and execute custom user-defined events."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
# typing imports
from typing import Any, Optional
from .persistence import PersistenceService

# Bot type replaced with Any for compatibility
Bot = Any


class EventScheduler:
    """Loads scheduled events from DB and triggers them when due."""

    def __init__(
        self,
        bot: Bot,
        storage: PersistenceService,
    ) -> None:
        self.bot = bot
        self.storage = storage
        self._task: Optional[asyncio.Task[Any]] = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self.logger = logging.getLogger("EventScheduler")

    def start(self) -> None:
        """Start the scheduler loop."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run_loop(), name="event-scheduler")
            self.logger.info("Started EventScheduler loop")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.logger.info("Stopped EventScheduler loop")

    async def _run_loop(self) -> None:
        """Main loop to check and execute due events."""
        while not self._stop_event.is_set():
            try:
                self.logger.debug("Scanning scheduled events")
                await self._check_and_run()
            except Exception:
                self.logger.exception("Unhandled error in scheduler loop")
            # wait before next scan
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                continue

    async def _check_and_run(self) -> None:
        """Fetch events and execute those whose next_run is due."""
        now = datetime.now(timezone.utc)
        # Query only events that are due as of now
        events = self.storage.list_due_events(now_iso=now.isoformat())
        self.logger.debug("Due events to execute: %d", len(events))
        for ev in events:
            self.logger.info(
                "Event due: id=%s next_run=%s command=%s",
                ev.get('id'), ev.get('next_run'), ev.get('command')
            )
            # execute event
            await self._execute_event(ev)
            # schedule next: prefer anchor+expr if present
            anchor = ev.get('schedule_anchor')
            expr = ev.get('schedule_expr')
            if anchor and expr:
                try:
                    from .schedule_expression import compute_next_run_from_anchor
                    new_run, _ = compute_next_run_from_anchor(anchor, expr, now=now)
                except Exception:
                    minutes = max(1, int(ev.get('interval_minutes') or 0))
                    new_run = now + timedelta(minutes=minutes)
            else:
                minutes = max(1, int(ev.get('interval_minutes') or 0))
                new_run = now + timedelta(minutes=minutes)
            # persist next_run back to DB
            session = self.storage.db.GetSession()
            try:
                from ..db.models import ScheduledEvent
                db_ev = session.get(ScheduledEvent, ev['id'])
                if db_ev:
                    setattr(db_ev, 'next_run', new_run)
                    session.commit()
            finally:
                session.close()

    async def _execute_event(self, ev: dict[str, Any]) -> None:
        """Execute a single scheduled event by sending its command to the channel."""
        channel_id = ev.get('channel_id')
        command = ev.get('command')
        if channel_id is None or not command:
            return
        chan = self.bot.get_channel(channel_id)
        if chan is None:
            try:
                chan = await self.bot.fetch_channel(channel_id)  # type: ignore[attr-defined]
            except Exception:
                self.logger.exception("fetch_channel(%s) failed", channel_id)
                return
        try:
            # dispatch via approved scheduled reports registry
            from ..services.reporting import schedulable_reports

            # For commands with parameters (like reminder:<text>), map to base key
            lookup = command
            if isinstance(command, str) and ":" in command:
                lookup = command.split(":", 1)[0]

            func = schedulable_reports.get(lookup)
            if not func:
                self.logger.warning("Scheduled report not found: %s (original: %s)", lookup, command)
            else:
                self.logger.info("Executing scheduled report %s (orig: %s) in channel %s", lookup, command, channel_id)
                # Send a mention before the report according to mention_type (default: none)
                mention_type = (ev.get('mention_type') or 'none').lower()
                try:
                    if mention_type == 'everyone':
                        await chan.send("@everyone")
                    elif mention_type == 'here':
                        await chan.send("@here")
                    elif mention_type == 'user':
                        target = ev.get('target_user_id')
                        if target and str(target).isdigit():
                            await chan.send(f"<@{target}>")
                    else:
                        # 'none' or unknown: no pre-mention
                        pass
                except Exception:
                    self.logger.warning("Failed to send mention for event %s", ev.get('id'))
                # Call handler; pass event dict when supported
                try:
                    result = func(self.bot, chan, ev)
                except TypeError:
                    result = func(self.bot, chan)
                if asyncio.iscoroutine(result):
                    await result
        except Exception:
            self.logger.exception("Failed executing scheduled report '%s'", command)