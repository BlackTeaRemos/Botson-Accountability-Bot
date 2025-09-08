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
            # Sleep for configured interval, defaulting to at least 60s
            wait_seconds = max(60, int(getattr(self.config, 'scheduled_report_interval_minutes', 1) or 1) * 60)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=wait_seconds)
            except asyncio.TimeoutError:
                # timeout means continue the next cycle
                pass
