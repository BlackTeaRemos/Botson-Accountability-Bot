"""Small utilities used by command modules.
"""

from typing import Any, Dict, cast


def JsonDumpsCompact(data: Any) -> str:
    """Serialize `data` to compact JSON with stable key ordering.

    Args:
        data (Any): Arbitrary JSON-serializable data.

    Returns:
        str: Compact JSON string with sorted keys.
    """
    import json

    return json.dumps(data, separators=(",", ":"), sort_keys=True)

def FormatDiagnosticsMarkdown(snapshot: Dict[str, Any]) -> str:
    """Stub for rendering a concise diagnostics summary.

    This is a placeholder implementation that raises NotImplementedError to
    indicate the formatting logic has not been implemented yet.

    Args:
        snapshot (Dict[str, Any]): Diagnostics snapshot as returned by
            DiagnosticsService.collect().

    Returns:
        str: Readable diagnostics summary suitable for sending as a message.

    Raises:
        NotImplementedError: Always raised by this stub.

    Examples:
        >>> FormatDiagnosticsMarkdown({})
        Traceback (most recent call last):
            ...
        NotImplementedError: FormatDiagnosticsMarkdown is not implemented.
    """
    raise NotImplementedError("FormatDiagnosticsMarkdown is not implemented.")
