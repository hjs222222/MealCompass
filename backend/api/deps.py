"""HTTP dependency providers."""

from core.config import Settings, get_settings


def get_app_settings() -> Settings:
    """Return the process application settings."""
    return get_settings()


def tracing_degraded(settings: Settings) -> bool:
    """Return whether optional tracing is unavailable for the current settings."""
    return not settings.tracing_enabled
