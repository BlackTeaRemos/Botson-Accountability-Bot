"""Background scheduler for periodic report posting.

This scheduler is separate from the custom EventScheduler. It periodically
posts a compact weekly embed to the configured channels.
"""

from __future__ import annotations

import asyncio
from typing import Optional, TYPE_CHECKING

try:  # Runtime imports (may not be available during static analysis)
    import discord  # type: ignore
except Exception:  # pragma: no cover
    discord = None  # type: ignore

if TYPE_CHECKING:  # Only for type-checkers
    from discord.ext.commands import Bot  # type: ignore

from ..core.config import AppConfig
from .persistence import PersistenceService
from .reporting import ReportingService, schedulable_reports


class ReportScheduler:
    """Runs an interval loop to post weekly embed reports.

    Behavior: Every N minutes, for each target channel, generate weekly structured
    data and post a Discord embed. Errors are logged and the loop keeps running.
    """

    def __init__(
        self,
        bot: "Bot",
        storage: PersistenceService,
        reporting: ReportingService,
        config: AppConfig,
    ) -> None:
        self.bot = bot
        self.storage = storage
        self.reporting = reporting
        self.config = config
        self._task: Optional[asyncio.Task[None]] = None
        self._posting: asyncio.Lock = asyncio.Lock()
        self._stopped = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._run_loop(), name="report-scheduler")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                # Serialize posting cycles so we don't overlap on slow networks
                async with self._posting:
                    await self._post_cycle()
            except Exception as e:
                print(f"[Scheduler] Unexpected error during post cycle: {e}")
            # Sleep for configured interval, defaulting to at least 60s
            wait_seconds = max(60, int(getattr(self.config, 'scheduled_report_interval_minutes', 1) or 1) * 60)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=wait_seconds)
            except asyncio.TimeoutError:
                # timeout means continue the next cycle
                pass

    async def _post_cycle(self) -> None:
        # Determine target channels: configured list or all registered
        # Carefully coerce to tuple[int, ...] to satisfy type checkers
        raw_ids = getattr(self.config, 'scheduled_report_channel_ids', ())
        try:
            channel_ids: tuple[int, ...] = tuple(int(x) for x in (raw_ids or ()))  # type: ignore[arg-type]
        except Exception:
            channel_ids = tuple()
        if not channel_ids:
            try:
                channel_ids = tuple(self.storage.list_active_channel_ids())
            except Exception as e:
                print(f"[Scheduler] Failed to list channels: {e}")
                return
        for channel_id in channel_ids:
            try:
                await self._post_weekly_embed(channel_id)
            except Exception as e:
                print(f"[Scheduler] Channel {channel_id} cycle failed: {e}")

    async def _post_weekly_embed(self, channel_id: int) -> None:
        # Resolve channel
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)  # type: ignore[attr-defined]
            except Exception as e:
                print(f"[Scheduler] fetch_channel({channel_id}) failed: {e}")
                return
        # Proactively purge malformed date rows for this channel
        try:
            bad_dates = self.storage.detect_non_iso_dates(channel_id)
            if bad_dates:
                deleted_count, _ = self.storage.purge_non_iso_dates(channel_id)
                if deleted_count:
                    print(f"[Scheduler] Purged {deleted_count} malformed daily rows in channel {channel_id}.")
        except Exception as e:
            print(f"[Scheduler] Purge check failed for channel {channel_id}: {e}")
        # Delegate to the centralized new embed reporting
        try:
            func = schedulable_reports.get("weekly_embed")
            if not func:
                print("[Scheduler] 'weekly_embed' report not registered; skipping.")
                return
            result = func(self.bot, channel)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            print(f"[Scheduler] weekly_embed failed for channel {channel_id}: {e}")
