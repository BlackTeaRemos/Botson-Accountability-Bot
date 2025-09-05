from __future__ import annotations
from typing import Optional, Any, Dict, List, cast
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from ..db.connection import Database
from ..db.models import Channel, Message, HabitDailyScore, HabitMessageScore, GuildSetting

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
        """Rebuild per-day aggregates from per-message scores."""
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

            # Recompute from message scores
            if date:
                # Single date
                raw_ratio_col = getattr(HabitMessageScore, "raw_ratio")  # type: ignore[attr-defined]
                result = cast(List[Any], session.query(
                    HabitMessageScore.user_id,
                    HabitMessageScore.date,
                    func.sum(raw_ratio_col).label('raw_score_sum'),
                    func.count(HabitMessageScore.id).label('messages_count')
                ).filter(
                    and_(
                        HabitMessageScore.channel_id == channel.id,
                        HabitMessageScore.date == date
                    )
                ).group_by(
                    HabitMessageScore.user_id,
                    HabitMessageScore.date
                ).all())

                for row in result:
                    daily_score = HabitDailyScore(
                        user_id=str(getattr(row, 'user_id')),
                        date=str(getattr(row, 'date')),
                        channel_id=channel.id,
                        raw_score_sum=float(getattr(row, 'raw_score_sum') or 0.0),
                        normalized_score=0.0,
                        messages_count=int(getattr(row, 'messages_count') or 0)
                    )
                    session.add(daily_score)
            else:
                # All dates
                raw_ratio_col2 = getattr(HabitMessageScore, "raw_ratio")  # type: ignore[attr-defined]
                result = cast(List[Any], session.query(
                    HabitMessageScore.user_id,
                    HabitMessageScore.date,
                    func.sum(raw_ratio_col2).label('raw_score_sum'),
                    func.count(HabitMessageScore.id).label('messages_count')
                ).filter(
                    HabitMessageScore.channel_id == channel.id
                ).group_by(
                    HabitMessageScore.user_id,
                    HabitMessageScore.date
                ).all())

                for row in result:
                    daily_score = HabitDailyScore(
                        user_id=str(getattr(row, 'user_id')),
                        date=str(getattr(row, 'date')),
                        channel_id=channel.id,
                        raw_score_sum=float(getattr(row, 'raw_score_sum') or 0.0),
                        normalized_score=0.0,
                        messages_count=int(getattr(row, 'messages_count') or 0)
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
