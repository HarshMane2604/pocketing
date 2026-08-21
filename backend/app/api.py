"""HTTP and WebSocket routes."""

from dataclasses import field
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_session
from app.models import Attachment, Note, ThreadMessage
from app.realtime import connections
from app.schemas import (
    NoteResponse,
    NoteUpdate,
    ReorderRequest,
    ThreadMessageResponse,
)
from app.service import (
    cleanup_attachment_files,
    create_note,
    create_thread_message,
    delete_upload_file,
    get_thread_count,
    get_thread_counts,
    serialize_note,
    serialize_thread_message,
)
from app.telegram import telegram_bridge

settings = get_settings()

router = APIRouter(prefix="/api", tags=["notes"])
websocket_router = APIRouter()


async def get_note_or_404(note_id: int, session: AsyncSession) -> Note:
    note = await session.get(Note, note_id, options=[selectinload(Note.attachments)])
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


# ── Notes ──


@router.get("/notes", response_model=list[NoteResponse])
async def list_notes(
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    query = select(Note).options(selectinload(Note.attachments))
    if search and search.strip():
        query = query.where(Note.content.ilike(f"%{search.strip()}%"))
    query = query.order_by(
        Note.is_done.asc(),
        (Note.priority == 0).asc(),
        Note.priority.asc(),
        Note.is_pinned.desc(),
        Note.created_at.desc(),
        Note.id.desc(),
    )
    result = await session.execute(query)
    notes = list(result.scalars().all())

    # Batch-fetch thread counts
    note_ids = [n.id for n in notes]
    counts = await get_thread_counts(session, note_ids)

    return [serialize_note(n, counts.get(n.id, 0)) for n in notes]


@router.post("/notes", response_model=NoteResponse, status_code=201)
async def add_note(
    content: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    session: AsyncSession = Depends(get_session),
) -> dict:
    content = content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Note cannot be empty")
    if len(content) > 4000:
        raise HTTPException(status_code=422, detail="Note too long (max 4000 chars)")

    note = await create_note(session, content, files=files if files else None)

    # Send text to Telegram
    await telegram_bridge.send_message(note.content)

    # Send each file to Telegram
    if note.attachments:
        upload_dir = Path(settings.upload_dir)
        for att in note.attachments:
            file_path = upload_dir / att.storage_key
            await telegram_bridge.send_file(
                file_path=file_path,
                filename=att.filename,
                caption=f"📎 {att.filename}",
            )

    return serialize_note(note, 0)


@router.put("/notes/reorder", status_code=204)
async def reorder_notes(
    req: ReorderRequest,
    session: AsyncSession = Depends(get_session),
) -> Response:
    query = select(Note).where(Note.id.in_(req.note_ids)).options(selectinload(Note.attachments))
    result = await session.execute(query)
    notes_by_id = {n.id: n for n in result.scalars().all()}

    for index, note_id in enumerate(req.note_ids):
        if note_id in notes_by_id:
            note = notes_by_id[note_id]
            if note.priority != index + 1:
                note.priority = index + 1
                tc = await get_thread_count(session, note.id)
                # Broadcast each update individually
                await connections.broadcast({"type": "note.updated", "note": serialize_note(note, tc)})

    await session.commit()
    return Response(status_code=204)


@router.patch("/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    note_in: NoteUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    note = await get_note_or_404(note_id, session)
    for field, value in note_in.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    await session.commit()
    await session.refresh(note, attribute_names=["attachments"])
    tc = await get_thread_count(session, note.id)
    await connections.broadcast({"type": "note.updated", "note": serialize_note(note, tc)})
    return serialize_note(note, tc)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    note = await get_note_or_404(note_id, session)
    # Collect attachment files to clean up after delete
    attachments_to_clean = list(note.attachments) if note.attachments else []
    # Also collect thread message attachments
    thread_query = select(ThreadMessage).where(ThreadMessage.note_id == note_id).options(
        selectinload(ThreadMessage.attachments)
    )
    thread_result = await session.execute(thread_query)
    for tm in thread_result.scalars().all():
        if tm.attachments:
            attachments_to_clean.extend(tm.attachments)

    await session.delete(note)
    await session.commit()
    # Clean up files from disk after successful DB delete
    cleanup_attachment_files(attachments_to_clean)
    await connections.broadcast({"type": "note.deleted", "id": note_id})
    return Response(status_code=204)


# ── Thread endpoints ──


@router.get("/notes/{note_id}/thread", response_model=list[ThreadMessageResponse])
async def list_thread_messages(
    note_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await get_note_or_404(note_id, session)
    query = (
        select(ThreadMessage)
        .where(ThreadMessage.note_id == note_id)
        .options(selectinload(ThreadMessage.attachments))
        .order_by(ThreadMessage.created_at.asc(), ThreadMessage.id.asc())
    )
    result = await session.execute(query)
    messages = list(result.scalars().all())
    return [serialize_thread_message(m) for m in messages]


@router.post("/notes/{note_id}/thread", response_model=ThreadMessageResponse, status_code=201)
async def add_thread_message(
    note_id: int,
    content: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    session: AsyncSession = Depends(get_session),
) -> dict:
    content = content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Thread message cannot be empty")
    if len(content) > 4000:
        raise HTTPException(status_code=422, detail="Message too long (max 4000 chars)")

    note = await get_note_or_404(note_id, session)
    message = await create_thread_message(session, note, content, files=files if files else None)

    # Send thread reply to Telegram
    preview = note.content[:50] + ("…" if len(note.content) > 50 else "")
    await telegram_bridge.send_message(f"💬 Re: {preview}\n{content}")

    # Send each file to Telegram
    if message.attachments:
        upload_dir = Path(settings.upload_dir)
        for att in message.attachments:
            file_path = upload_dir / att.storage_key
            await telegram_bridge.send_file(
                file_path=file_path,
                filename=att.filename,
                caption=f"💬📎 Re: {preview}",
            )

    return serialize_thread_message(message)


@router.delete("/notes/{note_id}/thread/{message_id}", status_code=204)
async def delete_thread_message(
    note_id: int,
    message_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await get_note_or_404(note_id, session)
    message = await session.get(
        ThreadMessage, message_id, options=[selectinload(ThreadMessage.attachments)]
    )
    if message is None or message.note_id != note_id:
        raise HTTPException(status_code=404, detail="Thread message not found")

    attachments_to_clean = list(message.attachments) if message.attachments else []
    await session.delete(message)
    await session.commit()
    cleanup_attachment_files(attachments_to_clean)
    thread_count = await get_thread_count(session, note_id)
    await connections.broadcast({
        "type": "thread.deleted",
        "message_id": message_id,
        "note_id": note_id,
        "thread_count": thread_count,
    })
    return Response(status_code=204)


# ── File management ──


@router.get("/files")
async def list_files(
    search: str | None = None,
    type: str | None = None,
    sort: str = "newest",
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Browse all attachments with search, type filter, sort, and pagination."""
    from app.schemas import FileSearchResult

    query = select(Attachment).options(
        selectinload(Attachment.note),
        selectinload(Attachment.thread_message),
    )

    # Filter by filename
    if search and search.strip():
        query = query.where(Attachment.filename.ilike(f"%{search.strip()}%"))

    # Filter by media type category
    type_prefixes = {
        "image": "image/",
        "video": "video/",
        "audio": "audio/",
        "document": None,  # handled specially
    }
    if type and type in type_prefixes:
        if type == "document":
            query = query.where(
                ~Attachment.content_type.startswith("image/"),
                ~Attachment.content_type.startswith("video/"),
                ~Attachment.content_type.startswith("audio/"),
            )
        else:
            query = query.where(Attachment.content_type.startswith(type_prefixes[type]))

    # Sort
    sort_map = {
        "newest": Attachment.created_at.desc(),
        "oldest": Attachment.created_at.asc(),
        "largest": Attachment.size_bytes.desc(),
        "smallest": Attachment.size_bytes.asc(),
        "name": Attachment.filename.asc(),
    }
    order = sort_map.get(sort, Attachment.created_at.desc())
    query = query.order_by(order)

    # Pagination
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    query = query.limit(limit).offset(offset)

    result = await session.execute(query)
    attachments = list(result.scalars().all())

    files_out: list[dict] = []
    for att in attachments:
        if att.note_id and att.note:
            parent_type = "note"
            parent_id = att.note_id
            content = att.note.content
        elif att.thread_message_id and att.thread_message:
            parent_type = "thread"
            parent_id = att.thread_message.note_id  # note the thread belongs to
            content = att.thread_message.content
        else:
            parent_type = "note"
            parent_id = att.note_id or 0
            content = ""

        parent_content = content[:80] + ("…" if len(content) > 80 else "")

        files_out.append(
            FileSearchResult(
                id=att.id,
                filename=att.filename,
                content_type=att.content_type,
                size_bytes=att.size_bytes,
                url=f"/api/files/{att.storage_key}",
                created_at=att.created_at,
                parent_type=parent_type,
                parent_id=parent_id,
                parent_content=parent_content,
            ).model_dump(mode="json")
        )

    return files_out

# --file_metadata_info--

@router.get("/files/{file_id}/info")
async def get_file_info(
    file_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """Return metadata for a specific uploaded file."""

    query = (
        select(Attachment)
        .where(Attachment.id == file_id)
        .options(
            selectinload(Attachment.note),
            selectinload(Attachment.thread_message)
        )
    )

    result = await session.execute(query)

    att = result.scalar_one_or_none()

    if att is None:
        raise HTTPException(status_code=404, detail="File not found")

    if att.note_id and att.note:
        parent_type = "note"
        parent_id = att.note_id
        parent_content = att.note.content
    elif att.thread_message_id and att.thread_message:
        parent_type = "thread"
        parent_id = att.thread_message_id
        parent_content = att.thread.content
    else:
        parent_type = None
        parent_id = None
        parent_content = ""
    
    return {
        "id": att.id,
        "filename": att.filename,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
        "url": f"/api/files/{att.storage_key}",
        "created_at": att.created_at.isoformat(),
        "parent_type": parent_type,
        "parent_id": parent_id,
        "parent_content": parent_content,
    }



# ── File serving ──
@router.get("/files/{storage_key}")
async def serve_file(
    storage_key: str,
    download: bool = False,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Serve an uploaded file. ?download=true forces download instead of inline."""
    # Validate the storage_key exists in DB
    query = select(Attachment).where(Attachment.storage_key == storage_key)
    result = await session.execute(query)
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = Path(settings.upload_dir) / storage_key
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")

    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=file_path,
        media_type=att.content_type,
        filename=att.filename,
        headers={"Content-Disposition": f'{disposition}; filename="{att.filename}"'},
    )

# ── File Delete ──
@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a single attachment."""
    att = await session.get(Attachment, file_id)
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    storage_key = att.storage_key
    note_id = att.note_id
    thread_message_id = att.thread_message_id

    await session.delete(att)
    await session.commit()
    delete_upload_file(storage_key)

    # Broadcast update so UI refreshes
    if note_id:
        note = await session.get(Note, note_id, options=[selectinload(Note.attachments)])
        if note:
            tc = await get_thread_count(session, note.id)
            await connections.broadcast({"type": "note.updated", "note": serialize_note(note, tc)})
    elif thread_message_id:
        msg = await session.get(
            ThreadMessage, thread_message_id, options=[selectinload(ThreadMessage.attachments)]
        )
        if msg:
            tc = await get_thread_count(session, msg.note_id)
            await connections.broadcast({
                "type": "thread.created",
                "message": serialize_thread_message(msg),
                "note_id": msg.note_id,
                "thread_count": tc,
            })

    return Response(status_code=204)

# ── File content extraction ──
@router.get("/files/{file_id}/content")
async def read_file_content(
    file_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Extract readable text from a stored file."""
    query = (
        select(Attachment)
        .where(Attachment.id == file_id)
    )

    result = await session.execute(query)

    att = result.scalar_one_or_none()

    if att is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = Path(settings.upload_dir) / att.storage_key

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="File not found on the disk",
        )

    # -------------------------------------------------
    # PDF
    # -------------------------------------------------

    if att.content_type == "application/pdf":
        try:
            import pymupdf
            doc = pymupdf.open(file_path)
            pages = []

            for page in doc:
                text = page.get_text()

                if text.strip():
                    pages.append(text)
            doc.close()
            extracted_text = "\n".join(pages).strip()

            return {
                "id": att.id,
                "filename": att.filename,
                "content_type": att.content_type,
                "text": extracted_text,
                "character_count": len(extracted_text),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to extract pdf: {e}"
            )
    
    # -------------------------------------------------
    # Plain text
    # -------------------------------------------------

    if att.content_type.startswith("text/"):
        try:
            extracted_text = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
            return {
                "id": att.id,
                "filename": att.filename,
                "content_type": att.content_type,
                "text": extracted_text,
                "character_count": len(extracted_text),
            }
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read text file: {exc}",
            )
    
    # -------------------------------------------------
    # Unsupported
    # -------------------------------------------------

    return {
        "id": att.id,
        "filename": att.filename,
        "content_type": att.content_type,
        "text": None,
        "error": "Text extraction is not supported for this file type yet.",
    }

# ── File send for Qwen ──
@router.post("/files/{file_id}/send")
async def send_file_to_telegram(file_id: int, session: AsyncSession=Depends(get_session,)) -> dict:
    """Send an existing Pocketing file to Telegram."""

    # find Attachment
    att = await session.get(Attachment, file_id)

    if att is None:
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )
    
    # Find Physical file
    upload_dir = Path(settings.upload_dir)
    file_path = upload_dir/att.storage_key

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="File not found on disk",
        )

    await telegram_bridge.send_file(
        file_path=file_path,
        filename=att.filename,
        caption=f"📎 {att.filename}",   
    )

    # Create a new note as a visible record of the send
    from datetime import datetime, timezone
    
    time_str = datetime.now(timezone.utc).astimezone().strftime("%I:%M %p")
    trace_note = Note(
        content=f"📤 `{att.filename}` sent to Telegram at {time_str}",
        source="system",
    )
    session.add(trace_note)
    await session.commit()
    await session.refresh(trace_note, attribute_names=["attachments"])
    
    await connections.broadcast({
        "type": "note.created",
        "note": serialize_note(trace_note, 0),
    })

    return {
        "status": "sent",
        "file_id": att.id,
        "filename": att.filename,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
    }


# ── WebSocket ──


@websocket_router.websocket("/ws")
async def websocket_updates(websocket: WebSocket) -> None:
    await connections.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connections.disconnect(websocket)
    except Exception:
        connections.disconnect(websocket)
