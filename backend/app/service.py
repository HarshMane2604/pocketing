"""Shared note operations for browser and messaging bridges."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting, Note
from app.realtime import connections
from app.schemas import NoteResponse


def serialize_note(note: Note) -> dict[str, object]:
    return NoteResponse.model_validate(note).model_dump(mode="json")


async def create_note(session: AsyncSession, content: str) -> Note:
    # WhatsApp Cloud API can be added as a webhook that validates Meta's
    # signature, extracts message text, and calls this same function.
    note = Note(content=content.strip())
    session.add(note)
    await session.commit()
    await session.refresh(note)
    await connections.broadcast({"type": "note.created", "note": serialize_note(note)})
    return note


async def get_setting(session: AsyncSession, key: str) -> str | None:
    setting = await session.get(AppSetting, key)
    return setting.value if setting else None


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    setting = await session.get(AppSetting, key)
    if setting is None:
        session.add(AppSetting(key=key, value=value))
    else:
        setting.value = value
    await session.commit()
