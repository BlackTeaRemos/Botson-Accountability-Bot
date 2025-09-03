"""Settings service for database-backed, editable configuration.

Provides CRUD-style helpers around the `settings` table with JSON value
encoding/decoding and simple validation. Sensitive keys are blocked.
"""

from __future__ import annotations

from typing import Any, Optional
import json
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..db.connection import Database
from ..db.models import Setting


BLOCKED_KEYS = {
    "discord_token",  # token must never be stored or edited via DB
    "token",
    "DISCORD_TOKEN",
}

AVAILABLE_SETTINGS: dict[str, dict[str, str]] = {
    # key: {type, description}
    "timezone": {
        "type": "str",
        "description": "IANA timezone string used for date calculations (e.g., 'America/New_York', 'UTC').",
    },
    "use_db_only": {
        "type": "bool",
        "description": "Enable DB-only mode for data operations (affects future features).",
    },
    "backfill_default_days": {
        "type": "int",
        "description": "Default days used when backfilling messages via commands.",
    },
    "guild_id": {
        "type": "int",
        "description": "Primary guild ID for fast command sync (optional).",
    },
    "daily_goal_tasks": {
        "type": "int",
        "description": "Target tasks per day that correspond to a full 5.0 normalized score.",
    },
    "scheduled_reports_enabled": {
        "type": "bool",
        "description": "Enable background weekly embed posting scheduler.",
    },
    "scheduled_report_interval_minutes": {
        "type": "int",
        "description": "Minutes between scheduled embed report posts.",
    },
    "scheduled_report_channel_ids": {
        "type": "list[int]",
        "description": "Explicit channel ID list for scheduler; if empty, all registered channels are used.",
    },
}


class SettingsService:
    """High-level API for bot configuration settings stored in DB.

    Contract:
    - Keys are case-sensitive strings without spaces. Use snake_case.
    - Values stored as JSON strings. Primitive types are allowed.
    - Blocked keys cannot be set or read via this service.
    """

    def __init__(self, db: Database):
        self.db = db

    def list_keys(self) -> list[str]:
        """Return all existing setting keys (excluding blocked)."""
        session: Session = self.db.get_session()
        try:
            rows = session.query(Setting.key).order_by(Setting.key.asc()).all()
            keys = [k for (k,) in rows if k not in BLOCKED_KEYS]
            return keys
        finally:
            session.close()

    def list_available_keys(self) -> list[str]:
        """Return supported setting keys you can configure via commands."""
        return sorted(AVAILABLE_SETTINGS.keys())

    def get_available_with_meta(self) -> list[dict[str, str]]:
        """Return available settings metadata for help output."""
        return [
            {"key": k, "type": v.get("type", ""), "description": v.get("description", "")}
            for k, v in sorted(AVAILABLE_SETTINGS.items())
        ]

    def get(self, key: str) -> Optional[Any]:
        """Return the value for key or None if absent. Raises on blocked."""
        self._ensure_key_allowed(key)
        session: Session = self.db.get_session()
        try:
            row = session.query(Setting).filter(Setting.key == key).first()
            if not row:
                return None
            try:
                raw_val = getattr(row, "value")
                return json.loads(str(raw_val))
            except Exception:
                # Fallback: return raw text
                return getattr(row, "value")
        finally:
            session.close()

    def set(self, key: str, value: Any) -> None:
        """Create or update setting value (JSON-encoded). Raises on blocked.

        Args:
            key: setting name (snake_case, letters/numbers/_)
            value: JSON-serializable value
        """
        self._ensure_key_allowed(key)
        self._validate_key_format(key)
        payload = json.dumps(value)
        session: Session = self.db.get_session()
        try:
            row = session.query(Setting).filter(Setting.key == key).first()
            if row:
                setattr(row, "value", payload)
                try:
                    setattr(row, "updated_at", func.current_timestamp())
                except Exception:
                    pass
            else:
                row = Setting(key=key, value=payload)
                session.add(row)
            session.commit()
        finally:
            session.close()

    def delete(self, key: str) -> bool:
        """Delete a setting. Returns True if a row was removed. Raises on blocked."""
        self._ensure_key_allowed(key)
        session: Session = self.db.get_session()
        try:
            row = session.query(Setting).filter(Setting.key == key).first()
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True
        finally:
            session.close()

    @staticmethod
    def _ensure_key_allowed(key: str) -> None:
        lowered = key.lower()
        if lowered in {k.lower() for k in BLOCKED_KEYS}:
            raise PermissionError("This setting is blocked and cannot be stored or edited.")

    @staticmethod
    def _validate_key_format(key: str) -> None:
        import re
        if not re.fullmatch(r"[a-z0-9_]+", key):
            raise ValueError("Key must be snake_case: lowercase letters, numbers, underscores only.")
