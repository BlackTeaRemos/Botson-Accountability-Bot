from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import text

Base = declarative_base()

class Channel(Base):
    """Channel registration model."""
    __tablename__ = 'channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_channel_id = Column(String, unique=True, nullable=False)
    registered_at = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    registered_by = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=True)

    # Relationships
    messages = relationship("Message", back_populates="channel")
    habit_daily_scores = relationship("HabitDailyScore", back_populates="channel")
    habit_message_scores = relationship("HabitMessageScore", back_populates="channel")

class Message(Base):
    """Discord message model."""
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_message_id = Column(String, unique=True, nullable=False)
    channel_id = Column(Integer, ForeignKey('channels.id'), nullable=False)
    author_id = Column(String, nullable=False)
    author_display = Column(String)
    created_at = Column(DateTime, nullable=False)
    edited_at = Column(DateTime)
    content = Column(Text, nullable=False)
    is_habit_candidate = Column(Boolean, nullable=False, default=False)
    parsed_at = Column(DateTime)
    raw_bracket_count = Column(Integer)
    filled_bracket_count = Column(Integer)
    parse_confidence = Column(Float)  # type: ignore[assignment]
    extracted_date = Column(String)

    # Relationships
    channel = relationship("Channel", back_populates="messages")
    habit_message_scores = relationship("HabitMessageScore", back_populates="message")

    # Indexes
    __table_args__ = (
        Index('idx_messages_channel_created', 'channel_id', 'created_at'),
    )

class HabitDailyScore(Base):
    """Daily habit score aggregation model."""
    __tablename__ = 'habit_daily_scores'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    date = Column(String, nullable=False)
    channel_id = Column(Integer, ForeignKey('channels.id'), nullable=False)
    raw_score_sum = Column(Float, nullable=False, default=0.0)  # type: ignore[assignment]
    normalized_score = Column(Float, nullable=False, default=0.0)  # type: ignore[assignment]
    messages_count = Column(Integer, nullable=False, default=0)
    last_updated = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))

    # Relationships
    channel = relationship("Channel", back_populates="habit_daily_scores")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('user_id', 'date', 'channel_id'),
        Index('idx_daily_scores_date', 'date'),
    )

class MonthlyTotal(Base):
    """Monthly habit totals model."""
    __tablename__ = 'monthly_totals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    month = Column(String, nullable=False)
    channel_id = Column(Integer, ForeignKey('channels.id'), nullable=False)
    normalized_sum = Column(Float, nullable=False, default=0.0)  # type: ignore[assignment]
    last_updated = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))

    # Relationships
    channel = relationship("Channel")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('user_id', 'month', 'channel_id'),
        Index('idx_monthly_totals_month', 'month'),
    )

class Report(Base):
    """Report generation model."""
    __tablename__ = 'reports'

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String, nullable=False)
    requested_at = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    generated_at = Column(DateTime)
    trigger = Column(String, nullable=False)
    range_start = Column(String)
    range_end = Column(String)
    artifact_path = Column(String)
    status = Column(String, nullable=False, default='pending')
    error = Column(Text)

class Run(Base):
    """Bot run tracking model."""
    __tablename__ = 'runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    completed_at = Column(DateTime)
    version = Column(String)
    diagnostics_json = Column(Text)
    status = Column(String, nullable=False)

class EventLog(Base):
    """Event logging model."""
    __tablename__ = 'events_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, nullable=False)
    occurred_at = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    correlation_id = Column(String)
    payload_json = Column(Text)
    context_json = Column(Text)

class HabitMessageScore(Base):
    """Per-message habit scoring model."""
    __tablename__ = 'habit_message_scores'

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(String, nullable=False)
    date = Column(String, nullable=False)
    channel_id = Column(Integer, ForeignKey('channels.id'), nullable=False)
    raw_ratio = Column(Float, nullable=False)  # type: ignore[assignment]
    filled_bracket_count = Column(Integer, nullable=False)
    total_bracket_count = Column(Integer, nullable=False)

    # Relationships
    message = relationship("Message", back_populates="habit_message_scores")
    channel = relationship("Channel", back_populates="habit_message_scores")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('message_id'),
        Index('idx_message_scores_date', 'date'),
    )

class GuildSetting(Base):
    """Guild-specific settings model."""
    __tablename__ = 'guild_settings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, unique=True, nullable=False)
    report_style = Column(String, nullable=False, default='style1')
    updated_at = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))


class Setting(Base):
    """Key-value settings stored in DB for runtime overrides.
    """
    __tablename__ = 'settings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False, unique=True)
    value = Column(Text, nullable=False, default='')
    created_at = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint('key'),
        Index('idx_settings_key', 'key'),
    )

class ScheduledEvent(Base):
    """Scheduled event model."""
    __tablename__ = 'scheduled_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, nullable=False)
    interval_minutes = Column(Integer, nullable=False)
    command = Column(String, nullable=False)
    next_run = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    active = Column(Boolean, nullable=False, default=True)
    schedule_expr = Column(String)  # e.g., "d2h4m30"
    schedule_anchor = Column(String)  # e.g., "week" | "month" | "year"
    target_user_id = Column(String)
    # Mention type: 'none' | 'user' | 'here' | 'everyone'
    mention_type = Column(String, nullable=False, default='user')

    def __repr__(self) -> str:
        return (
            f"<ScheduledEvent id={self.id} channel_id={self.channel_id} "
            f"interval={self.interval_minutes} command={self.command} next_run={self.next_run} "
            f"anchor={self.schedule_anchor} expr={self.schedule_expr} target={self.target_user_id} mention={self.mention_type} active={self.active}>"
        )
