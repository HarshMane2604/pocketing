"""Environment-backed application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./data/pocketing.db"
    frontend_origin: str = "http://localhost:5173"
    telegram_bot_token: str = ""
    telegram_allowed_chat_id: str = ""
    max_upload_size: int = 50 * 1024 * 1024  # 50 MB
    upload_dir: str = "data/uploads"

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.development"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
