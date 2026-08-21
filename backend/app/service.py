"""Shared note operations for browser and messaging bridges."""

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import AppSetting, Attachment, Note, ThreadMessage
from app.realtime import connections
from app.schemas import AttachmentResponse, NoteResponse, ThreadMessageResponse

settings = get_settings()


def _upload_path() -> Path:
    return Path(settings.upload_dir)


def serialize_attachment(att: Attachment) -> dict[str, object]:
    data = AttachmentResponse(
        id=att.id,
        filename=att.filename,
        content_type=att.content_type,
        size_bytes=att.size_bytes,
        url=f"/api/files/{att.storage_key}",
        created_at=att.created_at,
    ).model_dump(mode="json")
    return data


def serialize_note(note: Note, thread_count: int = 0) -> dict[str, object]:
    data = NoteResponse.model_validate(note).model_dump(mode="json")
    data["thread_count"] = thread_count
    # Include attachments if loaded
    if hasattr(note, "attachments") and note.attachments is not None:
        data["attachments"] = [serialize_attachment(a) for a in note.attachments]
    else:
        data["attachments"] = []
    return data


def serialize_thread_message(message: ThreadMessage) -> dict[str, object]:
    data = ThreadMessageResponse.model_validate(message).model_dump(mode="json")
    if hasattr(message, "attachments") and message.attachments is not None:
        data["attachments"] = [serialize_attachment(a) for a in message.attachments]
    else:
        data["attachments"] = []
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


def save_file_data(filename: str, content_type: str, data: bytes) -> tuple[str, str, int]:
    """Save raw file bytes to disk. Returns (storage_key, content_type, size_bytes).

    Used by Telegram bridge to persist downloaded media without an UploadFile.
    Raises ValueError if the data is empty or too large.
    """
    size = len(data)
    if size == 0:
        raise ValueError("Empty file data")
    if size > settings.max_upload_size:
        raise ValueError(f"File too large: {size} bytes (max {settings.max_upload_size})")

    ext = Path(filename).suffix.lower()
    storage_key = f"{uuid.uuid4().hex}{ext}"
    dest = _upload_path() / storage_key
    dest.write_bytes(data)
    return storage_key, content_type, size


async def save_upload(file: UploadFile) -> tuple[str, str, int]:
    """Save an uploaded file to disk. Returns (storage_key, content_type, size_bytes).

    Raises HTTPException if file exceeds max size.
    """
    # Read the file into memory (with size check)
    data = await file.read()
    size = len(data)
    if size > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_upload_size // (1024 * 1024)} MB",
        )
    if size == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Determine content type
    content_type = file.content_type or "application/octet-stream"

    # Generate storage key: uuid + original extension
    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()
    storage_key = f"{uuid.uuid4().hex}{ext}"

    # Write to disk
    dest = _upload_path() / storage_key
    dest.write_bytes(data)

    return storage_key, content_type, size


def delete_upload_file(storage_key: str) -> None:
    """Remove a file from disk (ignores if missing)."""
    path = _upload_path() / storage_key
    path.unlink(missing_ok=True)


async def create_attachments(
    session: AsyncSession,
    files: list[UploadFile],
    note_id: int | None = None,
    thread_message_id: int | None = None,
) -> list[Attachment]:
    """Save uploaded files and create Attachment records."""
    attachments: list[Attachment] = []
    for file in files:
        storage_key, content_type, size = await save_upload(file)
        att = Attachment(
            note_id=note_id,
            thread_message_id=thread_message_id,
            filename=file.filename or "upload",
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=size,
        )
        session.add(att)
        attachments.append(att)
    await session.flush()  # Get IDs assigned
    for att in attachments:
        await session.refresh(att)
    return attachments


def cleanup_attachment_files(attachments: list[Attachment]) -> None:
    """Remove files from disk for a list of attachments (used on cascade deletes)."""
    for att in attachments:
        delete_upload_file(att.storage_key)


async def create_note(
    session: AsyncSession,
    content: str,
    source: str = "web",
    created_at: datetime | None = None,
    files: list[UploadFile] | None = None,
    pre_attachments: list[Attachment] | None = None,
) -> Note:
    # WhatsApp Cloud API can be added as a webhook that validates Meta's
    # signature, extracts message text, and calls this same function.
    kwargs = {}
    if created_at is not None:
        kwargs["created_at"] = created_at
    note = Note(content=content.strip(), source=source, **kwargs)
    session.add(note)
    await session.flush()
    await session.refresh(note)

    # Handle file attachments from web uploads
    if files:
        await create_attachments(session, files, note_id=note.id)

    # Handle pre-built attachments (e.g. from Telegram bridge)
    if pre_attachments:
        for att in pre_attachments:
            att.note_id = note.id
            session.add(att)
        await session.flush()

    await session.commit()
    await session.refresh(note, attribute_names=["attachments"])
    await connections.broadcast({"type": "note.created", "note": serialize_note(note, 0)})
    return note


async def create_thread_message(
    session: AsyncSession,
    note: Note,
    content: str,
    files: list[UploadFile] | None = None,
) -> ThreadMessage:
    message = ThreadMessage(note_id=note.id, content=content.strip())
    session.add(message)
    await session.flush()
    await session.refresh(message)

    # Handle file attachments
    if files:
        await create_attachments(session, files, thread_message_id=message.id)

    await session.commit()
    await session.refresh(message, attribute_names=["attachments"])
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
