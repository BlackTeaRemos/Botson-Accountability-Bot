from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from sqlalchemy.orm import Session
from ..core.events import EventBus
from ..db.connection import Database
from ..db.models import Channel

try:  # Discord types only available at runtime inside bot environment
    import discord  # type: ignore
except Exception:  # pragma: no cover
    discord = None

class ChannelRegistrationService:
    """Manages channel registration and history backfill for habit tracking."""
    def __init__(self, bus: EventBus, db: Database, backfill_days: int):
        self.bus = bus
        self.db = db
        self.backfill_days = backfill_days

    def _insert_channel(self, discord_channel_id: int, registered_by: int):
        """Insert or update a channel registration."""
        session: Session = self.db.get_session()
        try:
            # Check if channel already exists
            existing_channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(discord_channel_id)
            ).first()

            if existing_channel:
                # Update existing channel to active
                existing_channel.active = True
                existing_channel.registered_by = str(registered_by)
            else:
                # Create new channel
                channel = Channel(
                    discord_channel_id=str(discord_channel_id),
                    registered_by=str(registered_by),
                    active=True
                )
                session.add(channel)

            session.commit()
        finally:
            session.close()

    async def register(self, discord_channel_id: int, user_id: int, backfill_days: Optional[int] = None):
        days = backfill_days or self.backfill_days
        self._insert_channel(discord_channel_id, user_id)
        await self.bus.emit(
            "ChannelRegistered",
            {
                "channel_id": discord_channel_id,
                "registered_by": user_id,
                "backfill_days": days,
            },
            {},
        )
        # TODO Actually implement this
        await self.bus.emit(
            "BackfillScheduled",
            {
                "channel_id": discord_channel_id,
                "since": (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat(),
            },
            {},
        )

    async def backfill_recent(self, channel: Any, days: int = 7, limit: int = 2000):
        """Backfill recent messages from a channel for the past given days.

        Emits MessageReceived events for each historical message in chronological order.
        This is a lightweight fetch limited by 'limit' to avoid heavy rate-limit impact.
        """
        if discord is None:
            return 0
        since_dt = datetime.now(tz=timezone.utc) - timedelta(days=days)
        count = 0
        # Fetch history (Discord returns newest first; we reverse for chronological processing)
        async for msg in channel.history(limit=limit, after=since_dt, oldest_first=True):
            if msg.author.bot:
                continue
            await self.bus.emit(
                "MessageReceived",
                {
                    "discord_message_id": msg.id,
                    "channel_id": channel.id,
                    "author_id": msg.author.id,
                    "author_display": getattr(msg.author, 'display_name', str(msg.author)),
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat(),
                    "backfilled": True,
                },
                {},
            )
            count += 1
        return count
