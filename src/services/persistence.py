from __future__ import annotations
from typing import Optional, Any, Dict, List, cast
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from ..db.connection import Database
from ..db.models import Channel, Message, HabitDailyScore, HabitMessageScore, GuildSetting, Report

class PersistenceService:
    def __init__(self, db: Database):
        self.db = db

    def is_channel_registered(self, discord_channel_id: int) -> bool:
        """Check if a Discord channel is registered."""
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                and_(Channel.discord_channel_id == str(discord_channel_id), Channel.active.is_(True))
            ).first()
            return channel is not None
        finally:
            session.close()

    def list_active_channel_ids(self) -> list[int]:
        """Return all active registered Discord channel IDs as integers.

        Returns:
            A list of channel ids. Non-numeric ids are skipped defensively.
        """
        session: Session = self.db.GetSession()
        try:
            rows = session.query(Channel.discord_channel_id).filter(Channel.active.is_(True)).all()
            ids: list[int] = []
            for (cid_str,) in rows:
                try:
                    ids.append(int(cid_str))
                except Exception:
                    # Skip non-numeric values
                    continue
            return ids
        finally:
            session.close()

    def insert_message(
        self,
        discord_message_id: int,
        channel_id: int,
        author_id: int,
        author_display: str,
        created_at: str,
        content: str,
    ) -> None:
        """Insert a new Discord message row if absent."""
        session: Session = self.db.GetSession()
        try:
            # Check if message already exists
            existing = session.query(Message).filter(
                Message.discord_message_id == str(discord_message_id)
            ).first()

            if existing:
                return

            # Get or create channel
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_id)
            ).first()

            if not channel:
                return

            # Parse created_at string to datetime for DateTime column
            try:
                created_dt = datetime.fromisoformat(created_at.replace('Z', ''))
            except Exception:
                # Fallback: store as naive datetime parsed best-effort
                created_dt = datetime.strptime(created_at[:19], "%Y-%m-%dT%H:%M:%S")

            # Create new message
            message = Message(
                discord_message_id=str(discord_message_id),
                channel_id=channel.id,
                author_id=str(author_id),
                author_display=author_display,
                created_at=created_dt,
                content=content
            )

            session.add(message)
            session.commit()
        finally:
            session.close()

    def update_habit_parse(
        self,
        discord_message_id: int,
        raw_bracket_count: int,
        filled_bracket_count: int,
        confidence: float,
        extracted_date: Optional[str],
    ) -> None:
        """Persist parse metadata for a message marked as habit candidate."""
        session: Session = self.db.GetSession()
        try:
            message = session.query(Message).filter(
                Message.discord_message_id == str(discord_message_id)
            ).first()

            if message:
                setattr(message, "is_habit_candidate", True)
                setattr(message, "parsed_at", func.current_timestamp())
                setattr(message, "raw_bracket_count", int(raw_bracket_count))
                setattr(message, "filled_bracket_count", int(filled_bracket_count))
                setattr(message, "parse_confidence", float(confidence))
                setattr(message, "extracted_date", extracted_date)
                session.commit()
        finally:
            session.close()

    def insert_or_replace_message_score(
        self,
        discord_message_id: int,
        user_id: int | str,
        date: str,
        channel_discord_id: int,
        raw_ratio: float,
        filled: int,
        total: int,
    ) -> None:
        """Upsert per-message scoring record (idempotent for edits)."""
        session: Session = self.db.GetSession()
        try:
            # Get message and channel
            message = session.query(Message).filter(
                Message.discord_message_id == str(discord_message_id)
            ).first()

            if not message:
                return

            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return

            # Check if score already exists
            existing_score = session.query(HabitMessageScore).filter(
                HabitMessageScore.message_id == message.id
            ).first()

            if existing_score:
                # Update existing
                setattr(existing_score, "raw_ratio", float(raw_ratio))
                setattr(existing_score, "filled_bracket_count", int(filled))
                setattr(existing_score, "total_bracket_count", int(total))
            else:
                # Create new
                score = HabitMessageScore(
                    message_id=message.id,
                    user_id=str(user_id),
                    date=date,
                    channel_id=channel.id,
                    raw_ratio=float(raw_ratio),
                    filled_bracket_count=int(filled),
                    total_bracket_count=int(total)
                )
                session.add(score)

            session.commit()
        finally:
            session.close()

    def recompute_daily_scores(self, channel_discord_id: int, date: str | None = None) -> None:
        """Rebuild per-day aggregates from per-message scores.
        """
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return

            # Delete existing daily scores
            query = session.query(HabitDailyScore).filter(
                HabitDailyScore.channel_id == channel.id
            )

            if date:
                query = query.filter(HabitDailyScore.date == date)

            query.delete()

            # Recompute from message scores using latest-per-day replacement logic
            # Load joined rows so we can pick the latest message per (user_id, date)
            from ..db.models import Message as _Message

            filters = [HabitMessageScore.channel_id == channel.id]
            if date:
                filters.append(HabitMessageScore.date == date)

            rows: List[Any] = cast(List[Any], session.query(
                HabitMessageScore,
                _Message.created_at,
                _Message.edited_at
            ).join(_Message, HabitMessageScore.message_id == _Message.id)
             .filter(and_(*filters)).all())

            # Group by (user_id, date)
            from collections import defaultdict
            grouped: Dict[tuple[str, str], list[tuple[Any, Any, Any]]] = defaultdict(list)
            for hms, created_at, edited_at in rows:
                key = (str(getattr(hms, 'user_id')), str(getattr(hms, 'date')))
                grouped[key].append((hms, created_at, edited_at))

            # For each group, select the latest record by (edited_at or created_at)
            for (user_id_val, date_val), items in grouped.items():
                def _ts(t: Any, c: Any) -> Any:
                    return t if t is not None else c
                # Compute messages count for transparency
                messages_count = len(items)
                latest = max(items, key=lambda tup: _ts(tup[2], tup[1]))
                latest_hms = latest[0]
                raw_ratio_value = float(getattr(latest_hms, 'raw_ratio') or 0.0)
                daily_score = HabitDailyScore(
                    user_id=str(user_id_val),
                    date=str(date_val),
                    channel_id=channel.id,
                    raw_score_sum=raw_ratio_value,
                    normalized_score=0.0,
                    messages_count=messages_count,
                )
                session.add(daily_score)

            session.commit()
        finally:
            session.close()

    def update_message_content(self, discord_message_id: int, new_content: str) -> None:
        """Update stored message content and clear prior parse so it can be re-parsed."""
        session: Session = self.db.GetSession()
        try:
            message = session.query(Message).filter(
                Message.discord_message_id == str(discord_message_id)
            ).first()

            if message:
                setattr(message, "content", new_content)
                setattr(message, "is_habit_candidate", False)
                setattr(message, "parsed_at", None)
                setattr(message, "raw_bracket_count", None)
                setattr(message, "filled_bracket_count", None)
                setattr(message, "parse_confidence", None)
                setattr(message, "extracted_date", None)
                session.commit()
        finally:
            session.close()

    def clear_current_week_scores(self, channel_discord_id: int) -> int:
        """Delete daily score rows for the current ISO week for a given channel."""
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return 0

            # Get current week
            from datetime import date
            today = date.today()
            iso_year, iso_week, _ = today.isocalendar()
            week_str = f"{iso_week - 1:02d}"

            # Count rows to delete
            count = session.query(HabitDailyScore).filter(
                and_(
                    HabitDailyScore.channel_id == channel.id,
                    func.strftime('%Y', HabitDailyScore.date) == str(iso_year),
                    func.strftime('%W', HabitDailyScore.date) == week_str
                )
            ).count()

            # Delete rows
            session.query(HabitDailyScore).filter(
                and_(
                    HabitDailyScore.channel_id == channel.id,
                    func.strftime('%Y', HabitDailyScore.date) == str(iso_year),
                    func.strftime('%W', HabitDailyScore.date) == week_str
                )
            ).delete()

            session.commit()
            return count
        finally:
            session.close()

    def get_guild_report_style(self, guild_id: int) -> str:
        """Get report style for a guild."""
        session: Session = self.db.GetSession()
        try:
            setting = session.query(GuildSetting).filter(
                GuildSetting.guild_id == str(guild_id)
            ).first()

            return cast(str, setting.report_style) if setting else "style1"
        finally:
            session.close()

    def set_guild_report_style(self, guild_id: int, style: str) -> None:
        """Set report style for a guild."""
        session: Session = self.db.GetSession()
        try:
            setting = session.query(GuildSetting).filter(
                GuildSetting.guild_id == str(guild_id)
            ).first()

            if setting:
                setattr(setting, "report_style", style)
            else:
                setting = GuildSetting(
                    guild_id=str(guild_id),
                    report_style=style
                )
                session.add(setting)

            session.commit()
        finally:
            session.close()

    def debug_add_score(self, user_id: str, date: str, channel_discord_id: int, delta: float) -> None:
        """Add (or create) a raw score delta to a user's day."""
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return

            # Try to find existing score
            existing = session.query(HabitDailyScore).filter(
                and_(
                    HabitDailyScore.user_id == str(user_id),
                    HabitDailyScore.date == date,
                    HabitDailyScore.channel_id == channel.id
                )
            ).first()

            if existing:
                current = float(getattr(existing, "raw_score_sum", 0.0))
                setattr(existing, "raw_score_sum", current + float(delta))
                setattr(existing, "last_updated", func.current_timestamp())
            else:
                score = HabitDailyScore(
                    user_id=str(user_id),
                    date=date,
                    channel_id=channel.id,
                    raw_score_sum=delta,
                    normalized_score=0.0,
                    messages_count=0
                )
                session.add(score)

            session.commit()
        finally:
            session.close()

    def debug_remove_score(self, user_id: str, date: str, channel_discord_id: int, delta: float) -> None:
        """Subtract raw score delta; clamps at zero."""
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return

            score = session.query(HabitDailyScore).filter(
                and_(
                    HabitDailyScore.user_id == str(user_id),
                    HabitDailyScore.date == date,
                    HabitDailyScore.channel_id == channel.id
                )
            ).first()

            if score:
                current_val = float(getattr(score, "raw_score_sum") or 0.0)
                new_val = max(0.0, current_val - float(delta))
                setattr(score, "raw_score_sum", new_val)
                setattr(score, "last_updated", func.current_timestamp())
                session.commit()
        finally:
            session.close()

    def debug_get_user_info(self, user_id: str, channel_discord_id: int) -> Dict[str, Any]:
        """Return aggregate info for a user in a channel."""
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return {"days": [], "total_raw": 0.0, "avg_raw": 0.0, "user_id": user_id}

            scores = session.query(HabitDailyScore).filter(
                and_(
                    HabitDailyScore.user_id == str(user_id),
                    HabitDailyScore.channel_id == channel.id
                )
            ).order_by(HabitDailyScore.date.desc()).limit(30).all()

            days_data: List[Dict[str, Any]] = []
            for s in scores:
                days_data.append({
                    "date": str(getattr(s, "date")),
                    "raw_score": float(getattr(s, "raw_score_sum") or 0.0),
                    "messages": int(getattr(s, "messages_count") or 0),
                })
            total = float(sum(float(getattr(s, "raw_score_sum") or 0.0) for s in scores))

            return {
                "days": days_data,
                "total_raw": total,
                "avg_raw": round(total / len(scores), 3) if scores else 0.0,
                "user_id": user_id,
            }
        finally:
            session.close()

    def purge_non_iso_dates(self, channel_discord_id: int) -> tuple[int, List[str]]:
        """Remove rows whose date column is not in ISO YYYY-MM-DD format."""
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return 0, []

            # Find non-ISO dates (hybrid approach via Python validation)
            scores_to_delete: List[HabitDailyScore] = []  # type: ignore[name-defined]
            deleted_dates: List[str] = []

            scores = session.query(HabitDailyScore).filter(
                HabitDailyScore.channel_id == channel.id
            ).all()

            for score in scores:
                date_str = str(getattr(score, "date"))
                if not (len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-'):
                    scores_to_delete.append(score)  # type: ignore[arg-type]
                    deleted_dates.append(date_str)

            # Delete scores and related message scores
            for score in scores_to_delete:
                session.delete(score)

            session.commit()
            return len(scores_to_delete), deleted_dates
        finally:
            session.close()

    def detect_non_iso_dates(self, channel_discord_id: int) -> List[str]:
        """Return list of date strings that are not ISO YYYY-MM-DD."""
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return []

            scores = session.query(HabitDailyScore).filter(
                HabitDailyScore.channel_id == channel.id
            ).all()

            bad: List[str] = []
            for score in scores:
                date_str = str(getattr(score, "date"))
                if not (len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-'):
                    bad.append(date_str)
            return bad
        finally:
            session.close()

    def debug_delete_all_reports(self) -> int:
        """Delete all reports from the database. Returns count of deleted reports."""
        session: Session = self.db.GetSession()
        try:
            count = session.query(Report).count()
            session.query(Report).delete()
            session.commit()
            return count
        finally:
            session.close()

    def debug_delete_test_users(self, channel_discord_id: int) -> Dict[str, int]:
        """Delete all test user data (messages, scores) for a channel. Returns counts of deleted items."""
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return {"messages": 0, "message_scores": 0, "daily_scores": 0}

            messages_query = session.query(Message).filter(
                and_(
                    Message.channel_id == channel.id,
                    Message.author_display.like("testuser_%")
                )
            )
            messages_count = messages_query.count()
            message_ids = [msg.id for msg in messages_query.all()]
            
            # Delete related message scores
            message_scores_count = 0
            if message_ids:
                message_scores_count = session.query(HabitMessageScore).filter(
                    HabitMessageScore.message_id.in_(message_ids)
                ).delete()
            
            # Delete daily scores for test users
            daily_scores_count = session.query(HabitDailyScore).filter(
                and_(
                    HabitDailyScore.channel_id == channel.id,
                    HabitDailyScore.user_id.like("testuser_%")
                )
            ).delete()
            
            # Delete the messages themselves
            messages_query.delete()
            
            session.commit()
            return {
                "messages": messages_count,
                "message_scores": message_scores_count,
                "daily_scores": daily_scores_count
            }
        finally:
            session.close()

    def debug_delete_all_user_data(self, channel_discord_id: int) -> Dict[str, int]:
        """Delete ALL user data (messages, scores) for a channel. Returns counts of deleted items.
        """
        session: Session = self.db.GetSession()
        try:
            channel = session.query(Channel).filter(
                Channel.discord_channel_id == str(channel_discord_id)
            ).first()

            if not channel:
                return {"messages": 0, "message_scores": 0, "daily_scores": 0}

            # Delete all messages for this channel
            messages_query = session.query(Message).filter(
                Message.channel_id == channel.id
            )
            messages_count = messages_query.count()
            message_ids = [msg.id for msg in messages_query.all()]
            
            # Delete related message scores
            message_scores_count = 0
            if message_ids:
                message_scores_count = session.query(HabitMessageScore).filter(
                    HabitMessageScore.message_id.in_(message_ids)
                ).delete()
            
            # Delete all daily scores for this channel
            daily_scores_count = session.query(HabitDailyScore).filter(
                HabitDailyScore.channel_id == channel.id
            ).delete()
            
            # Delete the messages themselves
            messages_query.delete()
            
            session.commit()
            return {
                "messages": messages_count,
                "message_scores": message_scores_count,
                "daily_scores": daily_scores_count
            }
        finally:
            session.close()
    
    def add_event(
        self,
        channel_discord_id: int,
        interval_minutes: int,
        command: str,
        *,
        schedule_anchor: str | None = None,
        schedule_expr: str | None = None,
        target_user_id: str | None = None,
        mention_type: str | None = 'user',
    ) -> int:
        """Add a new scheduled event.

        If schedule_anchor and schedule_expr are provided, next_run will be computed
        from the synchronized anchor; otherwise falls back to interval_minutes.
        """
        from ..db.models import ScheduledEvent
        from datetime import datetime, timedelta, timezone
        from .schedule_expression import compute_next_run_from_anchor

        session = self.db.GetSession()
        try:
            # compute next run as timezone-aware UTC datetime
            if schedule_anchor and schedule_expr:
                next_run, _ = compute_next_run_from_anchor(schedule_anchor, schedule_expr, now=datetime.now(timezone.utc))
            else:
                next_run = datetime.now(timezone.utc) + timedelta(minutes=interval_minutes)
            event = ScheduledEvent(
                channel_id=str(channel_discord_id),
                interval_minutes=interval_minutes,
                command=command,
                next_run=next_run,
                active=True,
                schedule_expr=schedule_expr,
                schedule_anchor=schedule_anchor,
                target_user_id=target_user_id,
                mention_type=mention_type or 'user',
            )
            session.add(event)
            session.commit()
            # event.id is primary key int
            return cast(int, event.id)
        finally:
            session.close()

    def list_events(
        self,
        channel_discord_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List active scheduled events, optionally filtered by channel."""
        from ..db.models import ScheduledEvent
        session = self.db.GetSession()
        try:

            query = session.query(ScheduledEvent).filter(ScheduledEvent.active.is_(True))
            if channel_discord_id is not None:
                query = query.filter(ScheduledEvent.channel_id == str(channel_discord_id))
            events = query.all()
            # convert each event to serializable dict
            result: list[dict[str, Any]] = []
            for e in events:
                result.append({
                    # e.id is primary key int
                    'id': cast(int, e.id),
                    'channel_id': int(str(e.channel_id)),
                    'interval_minutes': e.interval_minutes,
                    'command': e.command,
                    'next_run': e.next_run.isoformat(),
                    'schedule_expr': getattr(e, 'schedule_expr', None),
                    'schedule_anchor': getattr(e, 'schedule_anchor', None),
                    'target_user_id': getattr(e, 'target_user_id', None),
                    'mention_type': getattr(e, 'mention_type', 'user'),
                })
            return result
        finally:
            session.close()

    def list_due_events(
        self,
        *,
        now_iso: str | None = None,
        channel_discord_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List active scheduled events that are due (next_run <= now).

        Args:
            now_iso: Optional ISO8601 timestamp string for the cutoff time. If not provided, uses current UTC.
            channel_discord_id: Optional channel filter.

        Returns:
            List of event dicts similar to list_events(), but only those due for execution.
        """
        from ..db.models import ScheduledEvent
        from datetime import datetime, timezone
        session = self.db.GetSession()
        try:
            # Compute current UTC time if not provided
            if now_iso:
                try:
                    now_dt = datetime.fromisoformat(now_iso)
                except Exception:
                    now_dt = datetime.now(timezone.utc)
            else:
                now_dt = datetime.now(timezone.utc)
            query = session.query(ScheduledEvent).filter(ScheduledEvent.active.is_(True))
            if channel_discord_id is not None:
                query = query.filter(ScheduledEvent.channel_id == str(channel_discord_id))
            query = query.filter(ScheduledEvent.next_run <= now_dt)
            events = query.all()
            result: list[dict[str, Any]] = []
            for e in events:
                result.append({
                    'id': cast(int, e.id),
                    'channel_id': int(str(e.channel_id)),
                    'interval_minutes': e.interval_minutes,
                    'command': e.command,
                    'next_run': e.next_run.isoformat(),
                    'schedule_expr': getattr(e, 'schedule_expr', None),
                    'schedule_anchor': getattr(e, 'schedule_anchor', None),
                    'target_user_id': getattr(e, 'target_user_id', None),
                    'mention_type': getattr(e, 'mention_type', 'user'),
                })
            return result
        finally:
            session.close()

    def remove_event(
        self,
        event_id: int,
    ) -> bool:
        """Deactivate a scheduled event by id."""
        from ..db.models import ScheduledEvent
        session = self.db.GetSession()
        try:
            # load by primary key
            event = session.get(ScheduledEvent, event_id)
            if not event:
                return False
            # deactivate event
            setattr(event, "active", False)
            session.commit()
            return True
        finally:
            session.close()
