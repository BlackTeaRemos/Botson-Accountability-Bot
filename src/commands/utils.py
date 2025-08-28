"""Small utilities used by command modules."""

from typing import Any


def json_dumps_compact(data: Any) -> str:
    """Serialize `data` to compact JSON with stable key ordering.
    """
    import json

    return json.dumps(data, separators=(",", ":"), sort_keys=True)
