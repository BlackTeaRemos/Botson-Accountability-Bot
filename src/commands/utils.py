"""Small utilities used by command modules."""

from typing import Any


def JsonDumpsCompact(data: Any) -> str:
    """Serialize `data` to compact JSON with stable key ordering.
    """
    import json

    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def FormatDiagnosticsMarkdown(snapshot: Dict[str, Any]) -> str:
    """Render a concise, human-readable diagnostics summary for Discord.

    The returned string is plain text with simple sections. It is designed to
    stay well under Discord's 2000 character limit for typical payloads.

    Args:
        snapshot (dict): Diagnostics snapshot as returned by DiagnosticsService.collect().

    Returns:
        str: Readable diagnostics summary suitable for sending as a message.

    Examples:
        >>> fmt = FormatDiagnosticsMarkdown({
        ...     "database": {"status": "ok"},
        ...     "counts": {"channels": 2, "messages": 10, "habit_daily_scores": 5},
        ...     "disk": {"free_mb": 15360},
        ...     "storage": {"db_path": ":memory:"}
        ... })
        >>> isinstance(fmt, str)
        True
    """
    lines: list[str] = []

    # Title
    lines.append("Diagnostics summary")

    # Database status
    db_any: Any = snapshot.get("database", {})
    db: Dict[str, Any] = cast(Dict[str, Any], db_any) if isinstance(db_any, dict) else {}
    db_status = str(db.get("status", "unknown")).upper()
    db_error = db.get("error")
    lines.append(f"Database: {db_status}" + (f" - {db_error}" if db_error else ""))

    # Counts
    counts_any: Any = snapshot.get("counts", {})
    counts: Dict[str, Any] = cast(Dict[str, Any], counts_any) if isinstance(counts_any, dict) else {}
    if counts:
        ch = counts.get("channels")
        ms = counts.get("messages")
        ds = counts.get("habit_daily_scores")
        parts: list[str] = []
        if ch is not None:
            parts.append(f"channels={ch}")
        if ms is not None:
            parts.append(f"messages={ms}")
        if ds is not None:
            parts.append(f"daily_scores={ds}")
        if parts:
            lines.append("Counts: " + ", ".join(str(p) for p in parts))

    # Disk space
    disk_any: Any = snapshot.get("disk", {})
    disk: Dict[str, Any] = cast(Dict[str, Any], disk_any) if isinstance(disk_any, dict) else {}
    if "free_mb" in disk:
        try:
            free_mb = float(disk.get("free_mb", 0))
            free_gb = free_mb / 1024.0
            lines.append(f"Disk free: {free_gb:.2f} GB ({free_mb:.0f} MB)")
        except Exception:
            lines.append("Disk free: n/a")

    # Storage (db path, size)
    storage_any: Any = snapshot.get("storage", {})
    storage: Dict[str, Any] = cast(Dict[str, Any], storage_any) if isinstance(storage_any, dict) else {}
    if storage:
        db_path = storage.get("db_path")
        db_size_mb = storage.get("db_size_mb")
        if db_path:
            if db_size_mb is not None:
                try:
                    size_gb = float(db_size_mb) / 1024.0
                    lines.append(f"Database file: {db_path} ({size_gb:.3f} GB)")
                except Exception:
                    lines.append(f"Database file: {db_path}")
            else:
                lines.append(f"Database file: {db_path}")

    return "\n".join(lines)
