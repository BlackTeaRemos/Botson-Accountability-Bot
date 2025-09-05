from .dynaconf_settings import AppConfig, GetSettings

__all__ = ["AppConfig", "LoadConfig"]


def LoadConfig() -> AppConfig:
    """Load configuration using dynaconf.

    Returns:
        AppConfig: Instance with loaded values from settings files and environment.

    Example:
        config = LoadConfig()
        print(config.discord_token)
    """
    try:
        return GetSettings()
    except Exception as e:
        raise RuntimeError(f"Failed to load configuration: {e}") from e
