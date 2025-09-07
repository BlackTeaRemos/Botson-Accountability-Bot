"""Token validation helpers."""
from __future__ import annotations


def validate_discord_token(token: str) -> None:
    """Validate a Discord bot token and raise SystemExit on invalid.

    Args:
        token: The token string to validate.

    Raises:
        SystemExit: If token is missing or not in the expected format.
    """
    if not token or token == "" or token.lower() == "changeme":
        raise SystemExit("DISCORD_TOKEN not set in environment")
    parts = token.split('.')
    if len(parts) != 3:
        raise SystemExit(
            "DISCORD_TOKEN format unexpected (should contain 2 dots). Double-check the bot token, not client secret or application ID."
        )
