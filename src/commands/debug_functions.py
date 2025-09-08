"""Debug helper functions that can be reused by commands and tests.

This module contains a storage-parameterized implementation of the
GenerateRandomUserRecent helper and a factory to bind a PersistenceService
instance so callers get the original zero-arg form used by the command
registration code and tests.
"""
from typing import Any, Dict, List, Callable
import random
from datetime import datetime, timezone, timedelta


def _generate_random_user_recent_impl(
    storage,
    channel_discord_id: int,
    user_id: str | None = None,
    messages: int = 5,
    within_days: int = 7,
    cluster_days: int = 1,
    jitter_minutes: int = 120,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Implementation that requires an explicit PersistenceService.
    """
    # Prepare user id
    if user_id is None:
        user_id = f"testuser_{random.randint(1000, 9999)}"

    now = datetime.now(tz=timezone.utc)
    # pick a cluster center day within the allowed range
    days_back = random.randint(0, max(0, within_days - 1))
    center_date = (now - timedelta(days=days_back)).date()

    generated: List[Dict[str, Any]] = []
    for message_index in range(messages):
        # Choose a day within the cluster (0..cluster_days-1) anchored at center_date
        day_offset = random.randint(0, max(0, cluster_days - 1))
        entry_date = center_date - timedelta(days=day_offset)
        # Choose a time near midday for readability then add jitter
        base_dt = datetime.combine(entry_date, datetime.min.time()) + timedelta(hours=12)
        minute_jitter = random.randint(-jitter_minutes, jitter_minutes)
        created_at = base_dt + timedelta(
            minutes=minute_jitter + message_index
        )  # spread slightly across messages
        discord_message_id = random.randint(10**16, 10**18 - 1)
        extracted_date = entry_date.isoformat()
        payload: Dict[str, Any] = {
            "discord_message_id": discord_message_id,
            "channel_id": channel_discord_id,
            "author_id": str(user_id),
            "author_display": str(user_id),
            "content": "[x] Habit entry (generated)",
            "created_at": created_at.isoformat(),
            "extracted_date": extracted_date,
        }
        generated.append(payload)

    if dry_run:
        return {"user_id": user_id, "messages": generated, "written": False}

    # Ensure channel exists
    if not storage.is_channel_registered(channel_discord_id):
        raise ValueError(
            f"Channel {channel_discord_id} not registered. Register channel before writing test data."
        )

    # Insert into DB using persistence helpers
    dates_used: set[str] = set()
    for message_payload in generated:
        storage.insert_message(
            discord_message_id=message_payload["discord_message_id"],
            channel_id=message_payload["channel_id"],
            author_id=message_payload["author_id"],
            author_display=message_payload["author_display"],
            created_at=message_payload["created_at"],
            content=message_payload["content"],
        )
        # Persist a simple parse and per-message score (raw_ratio=1.0 -> counts as one)
        storage.update_habit_parse(
            message_payload["discord_message_id"],
            raw_bracket_count=1,
            filled_bracket_count=1,
            confidence=0.9,
            extracted_date=message_payload["extracted_date"],
        )
        storage.insert_or_replace_message_score(
            discord_message_id=message_payload["discord_message_id"],
            user_id=message_payload["author_id"],
            date=message_payload["extracted_date"],
            channel_discord_id=message_payload["channel_id"],
            raw_ratio=1.0,
            filled=1,
            total=1,
        )
        dates_used.add(message_payload["extracted_date"])

    # Recompute daily aggregates for the dates we touched
    for date_string in dates_used:
        storage.recompute_daily_scores(channel_discord_id=channel_discord_id, date=date_string)

    return {"user_id": user_id, "messages": generated, "written": True}


def make_generate_random_user_recent(storage) -> Callable[..., Dict[str, Any]]:
    """Return a callable with the same signature as the old module-level
    GenerateRandomUserRecent by binding the provided `storage` instance.

    This allows callers (like the debug command registration) to continue
    invoking the function with the same arguments they used previously.
    """

    def _bound(
        channel_discord_id: int,
        user_id: str | None = None,
        messages: int = 5,
        within_days: int = 7,
        cluster_days: int = 1,
        jitter_minutes: int = 120,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        return _generate_random_user_recent_impl(
            storage,
            channel_discord_id=channel_discord_id,
            user_id=user_id,
            messages=messages,
            within_days=within_days,
            cluster_days=cluster_days,
            jitter_minutes=jitter_minutes,
            dry_run=dry_run,
        )

    return _bound


__all__ = ["make_generate_random_user_recent", "_generate_random_user_recent_impl"]
