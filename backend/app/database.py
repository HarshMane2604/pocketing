"""Async SQLite engine and session lifecycle."""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def initialize_database() -> None:
    # The default SQLite URL points here. Creating it is harmless for custom URLs.
    Path("data").mkdir(exist_ok=True)
    from app.models import AppSetting, Note  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
