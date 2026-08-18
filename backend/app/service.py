"""Shared note operations for browser and messaging bridges."""

from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting, Note, ThreadMessage
from app.realtime import connections
from app.schemas import NoteResponse, ThreadMessageResponse


def serialize_note(note: Note, thread_count: int = 0) -> dict[str, object]:
    data = NoteResponse.model_validate(note).model_dump(mode="json")
    data["thread_count"] = thread_count
    return data


async def get_thread_count(session: AsyncSession, note_id: int) -> int:
    result = await session.execute(
        select(func.count()).where(ThreadMessage.note_id == note_id)
    )
    return result.scalar_one()


async def get_thread_counts(session: AsyncSession, note_ids: list[int]) -> dict[int, int]:
    """Get thread counts for multiple notes in a single query."""
    if not note_ids:
        return {}
    result = await session.execute(
        select(ThreadMessage.note_id, func.count())
        .where(ThreadMessage.note_id.in_(note_ids))
        .group_by(ThreadMessage.note_id)
    )
    return dict(result.all())


def serialize_thread_message(message: ThreadMessage) -> dict[str, object]:
    return ThreadMessageResponse.model_validate(message).model_dump(mode="json")


async def create_note(
    session: AsyncSession,
    content: str,
    source: str = "web",
    created_at: datetime | None = None,
) -> Note:
    # WhatsApp Cloud API can be added as a webhook that validates Meta's
    # signature, extracts message text, and calls this same function.
    kwargs = {}
    if created_at is not None:
        kwargs["created_at"] = created_at
    note = Note(content=content.strip(), source=source, **kwargs)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    await connections.broadcast({"type": "note.created", "note": serialize_note(note, 0)})
    return note


async def create_thread_message(
    session: AsyncSession,
    note: Note,
    content: str,
) -> ThreadMessage:
    message = ThreadMessage(note_id=note.id, content=content.strip())
    session.add(message)
    await session.commit()
    await session.refresh(message)
    thread_count = await get_thread_count(session, note.id)
    await connections.broadcast({
        "type": "thread.created",
        "message": serialize_thread_message(message),
        "note_id": note.id,
        "thread_count": thread_count,
    })
    return message


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
