"""Application configuration loaded from environment variables (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Fast Kanban service."""

    app_name: str = "Fast Kanban"
    database_url: str = "sqlite:///./kanban.db"
    database_echo: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance, loading it lazily on first use."""
    return Settings()
