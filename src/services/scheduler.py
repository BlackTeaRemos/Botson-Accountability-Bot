"""Background scheduler for periodic report posting."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

try:  # Runtime imports (may not be available during static analysis)
    import discord  # type: ignore
except Exception:  # pragma: no cover
    discord = None  # type: ignore

if TYPE_CHECKING:  # Only for type-checkers
    from discord.ext.commands import Bot  # type: ignore

from ..core.config import AppConfig
from .persistence import PersistenceService
from .reporting import ReportingService


class ReportScheduler:
    """Runs a simple interval loop to post weekly embed reports.

    Contract:
    - Inputs: bot, storage, reporting, config
    - Behavior: every N minutes, for each target channel, generate weekly structured
      data and post a Discord embed similar to /weekly_report_embed.
    - Errors: catches and logs channel-level failures; loop keeps running.
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
        interval_seconds = max(60, int(self.config.scheduled_report_interval_minutes) * 60)
        # initial small delay to let bot fully settle
        await asyncio.sleep(5)
        while not self._stopped.is_set():
            try:
                await self._post_reports_once()
            except Exception as e:
                print(f"[Scheduler] Unhandled error during post: {e}")
            # sleep with cancellation support
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue

    def _target_channel_ids(self) -> List[int]:
        # Explicit configured channels take precedence; else use all active registered
        if self.config.scheduled_report_channel_ids:
            return list(self.config.scheduled_report_channel_ids)
        return self.storage.list_active_channel_ids()

    async def _post_reports_once(self) -> None:
        if discord is None:
            return
        if self._posting.locked():
            # Skip if a previous cycle is still in progress
            print("[Scheduler] Previous cycle still running; skipping.")
            return
        async with self._posting:
            channel_ids = self._target_channel_ids()
            if not channel_ids:
                print("[Scheduler] No target channels to post into.")
                return
            for cid in channel_ids:
                try:
                    await self._post_embed_to_channel(cid)
                except Exception as e:
                    print(f"[Scheduler] Failed to post to channel {cid}: {e}")

    async def _post_embed_to_channel(self, channel_id: int) -> None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)  # type: ignore[attr-defined]
            except Exception as e:
                print(f"[Scheduler] fetch_channel({channel_id}) failed: {e}")
                return
        # Only send to text channels
        if not isinstance(channel, discord.TextChannel):  # type: ignore[attr-defined]
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

        # Build embed from reporting structured data
        dates, per_user, totals, warnings = self.reporting.get_weekly_structured(days=7)
        if not dates:
            # Nothing to post; remain quiet
            return
        human_dates = [datetime.strptime(d, '%Y-%m-%d').strftime('%b %d') for d in dates]
        embed = discord.Embed(  # type: ignore[attr-defined]
            title="Weekly Habit Report",
            description=f"Last {len(dates)} days",
            color=0x5865F2,
        )
        # Create compact lines similar to the command
        lines: list[str] = []
        for user_entry in per_user:
            uid = str(user_entry['user_id'])
            display = f"<@{uid}>" if uid.isdigit() else uid[:8]
            day_scores = [f"{user_entry.get(d,0):.1f}" for d in dates]
            total = user_entry['total']  # type: ignore[index]
            lines.append(f"{display} | {' '.join(day_scores)} | {total:.1f}")

        # Chunk to stay inside field limits
        chunk: list[str] = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > 950 and chunk:
                embed.add_field(name="Players", value="\n".join(chunk), inline=False)
                chunk = []
                current_len = 0
            chunk.append(line)
            current_len += len(line) + 1
        if chunk:
            embed.add_field(name="Players", value="\n".join(chunk), inline=False)

        totals_line = ' '.join(f"{totals[d]:.1f}" for d in dates)
        embed.add_field(name="Dates", value=' '.join(human_dates), inline=False)
        embed.add_field(name="Totals", value=totals_line, inline=False)
        if warnings:
            warn_join = "\n".join(warnings[:5]) + ("\n..." if len(warnings) > 5 else "")
            embed.add_field(name="Data Notes", value=warn_join[:1000], inline=False)
            if any('Dropped row' in w or 'unparseable date' in w for w in warnings):
                embed.add_field(
                    name="Action Required",
                    value=("Some rows were malformed and dropped. "
                           "Run /debug_purge_bad_dates in this channel to remove them."),
                    inline=False,
                )

        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[Scheduler] channel.send failed for {channel_id}: {e}")
