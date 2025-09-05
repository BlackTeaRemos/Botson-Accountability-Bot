from __future__ import annotations

from src.commands.utils import JsonDumpsCompact, FormatDiagnosticsMarkdown

def test_json_dumps_compact_sorting_and_compact():
    data = {"b": 2, "a": 1}
    s = JsonDumpsCompact(data)
    assert s == "{\"a\":1,\"b\":2}"


def test_format_diagnostics_markdown_happy_path():
    snapshot = {
        "database": {"status": "ok"},
        "counts": {"channels": 2, "messages": 10, "habit_daily_scores": 5},
        "disk": {"free_mb": 2048},
        "storage": {"db_path": ":memory:", "db_size_mb": 16},
    }
    out = FormatDiagnosticsMarkdown(snapshot)
    assert "Diagnostics summary" in out
    assert "Database: OK" in out
    assert "channels=2" in out and "messages=10" in out and "daily_scores=5" in out
    assert "Disk free:" in out
    assert ":memory:" in out


def test_format_diagnostics_markdown_resilience():
    # Missing or malformed sections should not raise and should still render something
    snapshot = {
        "database": {"status": "error", "error": "boom"},
        "counts": {"channels": None},
        "disk": {"free_mb": "not-a-number"},
        "storage": {"db_path": "db.sqlite"},
    }
    out = FormatDiagnosticsMarkdown(snapshot)
    assert "Database: ERROR - boom" in out
    assert "Diagnostics summary" in out
