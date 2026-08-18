"""HTTP and WebSocket routes."""

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Note, ThreadMessage
from app.realtime import connections
from app.schemas import (
    NoteCreate,
    NoteResponse,
    NoteUpdate,
    ReorderRequest,
    ThreadMessageCreate,
    ThreadMessageResponse,
)
from app.service import (
    create_note,
    create_thread_message,
    get_thread_count,
    get_thread_counts,
    serialize_note,
    serialize_thread_message,
)
from app.telegram import telegram_bridge

router = APIRouter(prefix="/api/notes", tags=["notes"])
websocket_router = APIRouter()


async def get_note_or_404(note_id: int, session: AsyncSession) -> Note:
    note = await session.get(Note, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    query = select(Note)
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


@router.post("", response_model=NoteResponse, status_code=201)
async def add_note(
    note_in: NoteCreate,
    session: AsyncSession = Depends(get_session),
) -> Note:
    note = await create_note(session, note_in.content)
    # Browser-created notes travel back to the paired phone. Telegram-origin
    # notes call create_note directly and therefore do not echo back.
    await telegram_bridge.send_message(note.content)
    return note


@router.put("/reorder", status_code=204)
async def reorder_notes(
    req: ReorderRequest,
    session: AsyncSession = Depends(get_session),
) -> Response:
    query = select(Note).where(Note.id.in_(req.note_ids))
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


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    note_in: NoteUpdate,
    session: AsyncSession = Depends(get_session),
) -> Note:
    note = await get_note_or_404(note_id, session)
    for field, value in note_in.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    await session.commit()
    await session.refresh(note)
    tc = await get_thread_count(session, note.id)
    await connections.broadcast({"type": "note.updated", "note": serialize_note(note, tc)})
    return note


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    note = await get_note_or_404(note_id, session)
    await session.delete(note)
    await session.commit()
    await connections.broadcast({"type": "note.deleted", "id": note_id})
    return Response(status_code=204)


# ── Thread endpoints ──


@router.get("/{note_id}/thread", response_model=list[ThreadMessageResponse])
async def list_thread_messages(
    note_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[ThreadMessage]:
    await get_note_or_404(note_id, session)
    query = (
        select(ThreadMessage)
        .where(ThreadMessage.note_id == note_id)
        .order_by(ThreadMessage.created_at.asc(), ThreadMessage.id.asc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


@router.post("/{note_id}/thread", response_model=ThreadMessageResponse, status_code=201)
async def add_thread_message(
    note_id: int,
    msg_in: ThreadMessageCreate,
    session: AsyncSession = Depends(get_session),
) -> ThreadMessage:
    note = await get_note_or_404(note_id, session)
    message = await create_thread_message(session, note, msg_in.content)
    # Send thread reply to Telegram under the same note context
    preview = note.content[:50] + ("…" if len(note.content) > 50 else "")
    await telegram_bridge.send_message(f"💬 Re: {preview}\n{msg_in.content}")
    return message


@router.delete("/{note_id}/thread/{message_id}", status_code=204)
async def delete_thread_message(
    note_id: int,
    message_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await get_note_or_404(note_id, session)
    message = await session.get(ThreadMessage, message_id)
    if message is None or message.note_id != note_id:
        raise HTTPException(status_code=404, detail="Thread message not found")
    await session.delete(message)
    await session.commit()
    thread_count = await get_thread_count(session, note_id)
    await connections.broadcast({
        "type": "thread.deleted",
        "message_id": message_id,
        "note_id": note_id,
        "thread_count": thread_count,
    })
    return Response(status_code=204)


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
