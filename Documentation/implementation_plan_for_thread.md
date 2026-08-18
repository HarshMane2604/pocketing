# Threads Feature — Detailed Implementation Plan

> **For the implementing model**: Follow each step in order. Each step has the exact file path, what to change, and the complete code. Do NOT skip steps. Do NOT deviate from the code provided.

---

## Step 1: Backend — Update `models.py`

**File**: `/home/harsh/pocketing/pocketing/backend/app/models.py`

**What to do**: Add a `ForeignKey` import and a new `ThreadMessage` model class after the existing `Note` class.

**Replace the entire file with**:

```python
"""SQLite models."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="web", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    thread_messages: Mapped[list["ThreadMessage"]] = relationship(
        "ThreadMessage", back_populates="note", cascade="all, delete-orphan", passive_deletes=True
    )


class ThreadMessage(Base):
    __tablename__ = "thread_messages"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    note: Mapped["Note"] = relationship("Note", back_populates="thread_messages")


class AppSetting(Base):
    """Tiny key/value store for bridge state such as the paired Telegram chat."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
```

**Key changes**:
- Added `ForeignKey` to imports from `sqlalchemy`
- Added `relationship` to imports from `sqlalchemy.orm`
- Added `thread_messages` relationship on `Note` with `cascade="all, delete-orphan"` and `passive_deletes=True`
- Added new `ThreadMessage` class with `id`, `note_id` (FK to `notes.id`), `content`, `created_at`
- Added reverse relationship `note` on `ThreadMessage`

---

## Step 2: Backend — Update `schemas.py`

**File**: `/home/harsh/pocketing/pocketing/backend/app/schemas.py`

**What to do**: Add `ThreadMessageCreate`, `ThreadMessageResponse` schemas and add `thread_count: int` to `NoteResponse`.

**Replace the entire file with**:

```python
"""API request and response types."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Note cannot be empty")
        return value


class NoteUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    is_pinned: bool | None = None
    is_done: bool | None = None
    priority: int | None = None

    @field_validator("content")
    @classmethod
    def strip_optional_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Note cannot be empty")
        return value


class ReorderRequest(BaseModel):
    note_ids: list[int]


class NoteResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    is_pinned: bool
    is_done: bool
    source: str
    priority: int
    thread_count: int = 0

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")


class ThreadMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Thread message cannot be empty")
        return value


class ThreadMessageResponse(BaseModel):
    id: int
    note_id: int
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
```

**Key changes**:
- Added `thread_count: int = 0` field to `NoteResponse`
- Added `ThreadMessageCreate` schema (content, 1–4000 chars, stripped)
- Added `ThreadMessageResponse` schema (id, note_id, content, created_at with ISO serializer)

---

## Step 3: Backend — Update `service.py`

**File**: `/home/harsh/pocketing/pocketing/backend/app/service.py`

**What to do**: Update `serialize_note` to include `thread_count`, and add a `create_thread_message` function.

**Replace the entire file with**:

```python
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
```

**Key changes**:
- `serialize_note` now accepts and includes `thread_count`
- Added `get_thread_count()` — single note thread count
- Added `get_thread_counts()` — batch thread counts for the list endpoint
- Added `serialize_thread_message()` helper
- Added `create_thread_message()` — creates message, broadcasts WebSocket event with `thread_count`
- Imported `func, select` from `sqlalchemy`
- Imported `ThreadMessage` from models and `ThreadMessageResponse` from schemas

---

## Step 4: Backend — Update `database.py`

**File**: `/home/harsh/pocketing/pocketing/backend/app/database.py`

**What to do**: Import `ThreadMessage` in `initialize_database()` so `create_all()` picks up the new table. Enable SQLite foreign key support.

**Replace the entire file with**:

```python
"""Async SQLite engine and session lifecycle."""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event, text
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


# Enable SQLite foreign key enforcement (required for ON DELETE CASCADE)
@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_fks(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def initialize_database() -> None:
    # The default SQLite URL points here. Creating it is harmless for custom URLs.
    Path("data").mkdir(exist_ok=True)
    from app.models import AppSetting, Note, ThreadMessage  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # create_all() does not add columns to an existing SQLite table.
        # Backfill the source field introduced in v1 without losing old notes.
        columns = await connection.execute(text("PRAGMA table_info(notes)"))
        column_names = {row[1] for row in columns}
        if "source" not in column_names:
            await connection.execute(
                text(
                    "ALTER TABLE notes ADD COLUMN source VARCHAR(20) "
                    "NOT NULL DEFAULT 'web'"
                )
            )
        if "priority" not in column_names:
            await connection.execute(
                text(
                    "ALTER TABLE notes ADD COLUMN priority INTEGER "
                    "NOT NULL DEFAULT 0"
                )
            )
```

**Key changes**:
- Added `event` to imports from `sqlalchemy`
- Added `_enable_sqlite_fks` listener to enable `PRAGMA foreign_keys=ON` (critical for SQLite cascade deletes)
- Added `ThreadMessage` to the import inside `initialize_database()`

---

## Step 5: Backend — Update `api.py`

**File**: `/home/harsh/pocketing/pocketing/backend/app/api.py`

**What to do**: Add thread endpoints and update list_notes to include thread counts.

**Replace the entire file with**:

```python
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
```

**Key changes**:
- `list_notes` now returns `list[dict]` and batch-fetches thread counts via `get_thread_counts()`
- `reorder_notes` and `update_note` include `thread_count` in their broadcasts
- Added 3 new thread endpoints: `GET /{note_id}/thread`, `POST /{note_id}/thread`, `DELETE /{note_id}/thread/{message_id}`
- Thread creation sends to Telegram with `💬 Re: [note preview]:\n[message]` format
- Thread deletion broadcasts `thread.deleted` event with updated `thread_count`
- Imported new models, schemas, and service functions

---

## Step 6: Frontend — Update `types.ts`

**File**: `/home/harsh/pocketing/pocketing/frontend/src/types.ts`

**Replace the entire file with**:

```typescript
export interface Note {
  id: number;
  content: string;
  created_at: string;
  is_pinned: boolean;
  is_done: boolean;
  source: 'web' | 'telegram';
  priority: number;
  thread_count: number;
}

export interface ThreadMessage {
  id: number;
  note_id: number;
  content: string;
  created_at: string;
}

export type NoteUpdate = Partial<Pick<Note, 'content' | 'is_pinned' | 'is_done' | 'priority'>>;

export type NoteEvent =
  | { type: 'note.created' | 'note.updated'; note: Note }
  | { type: 'note.deleted'; id: number }
  | { type: 'thread.created'; message: ThreadMessage; note_id: number; thread_count: number }
  | { type: 'thread.deleted'; message_id: number; note_id: number; thread_count: number };

export interface TelegramStatus {
  configured: boolean;
  running: boolean;
  chat_restricted: boolean;
  target_ready: boolean;
  last_error: string | null;
  last_message_at: string | null;
  last_sent_at: string | null;
}

export interface RuntimeStatus {
  status: string;
  telegram: TelegramStatus;
}
```

**Key changes**:
- Added `thread_count: number` to `Note` interface
- Added `ThreadMessage` interface
- Added `thread.created` and `thread.deleted` to `NoteEvent` union

---

## Step 7: Frontend — Update `api.ts`

**File**: `/home/harsh/pocketing/pocketing/frontend/src/api.ts`

**Replace the entire file with**:

```typescript
import type { Note, NoteUpdate, RuntimeStatus, ThreadMessage } from '@/types';

const configuredUrl = import.meta.env.VITE_API_URL?.replace(/\/$/, '');
const apiUrl = configuredUrl ?? '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const notesApi = {
  list: () => request<Note[]>('/api/notes'),
  status: () => request<RuntimeStatus>('/api/status'),
  create: (content: string) => request<Note>('/api/notes', {
    method: 'POST',
    body: JSON.stringify({ content }),
  }),
  update: (id: number, update: NoteUpdate) => request<Note>(`/api/notes/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(update),
  }),
  remove: (id: number) => request<void>(`/api/notes/${id}`, { method: 'DELETE' }),
  reorder: (noteIds: number[]) => request<void>('/api/notes/reorder', {
    method: 'PUT',
    body: JSON.stringify({ note_ids: noteIds }),
  }),
};

export const threadApi = {
  list: (noteId: number) => request<ThreadMessage[]>(`/api/notes/${noteId}/thread`),
  create: (noteId: number, content: string) => request<ThreadMessage>(`/api/notes/${noteId}/thread`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  }),
  remove: (noteId: number, messageId: number) => request<void>(`/api/notes/${noteId}/thread/${messageId}`, {
    method: 'DELETE',
  }),
};

export function websocketUrl(): string {
  if (configuredUrl) {
    const url = new URL(configuredUrl);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = '/ws';
    url.search = '';
    return url.toString();
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}
```

**Key changes**:
- Added `ThreadMessage` to import
- Added `threadApi` object with `list`, `create`, `remove` methods

---

## Step 8: Frontend — Update `Icons.tsx`

**File**: `/home/harsh/pocketing/pocketing/frontend/src/components/Icons.tsx`

**What to do**: Add `ThreadIcon` and `ArrowLeftIcon` exports. Add them **after** the existing `SendIcon` export at the end of the file.

**Add the following AFTER the last line (after the `SendIcon` closing):**

```typescript
/* Thread / chat bubble icon */
export const ThreadIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </Icon>
);

/* Back arrow icon */
export const ArrowLeftIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="m15 18-6-6 6-6" />
  </Icon>
);
```

---

## Step 9: Frontend — Update `NoteRow.tsx`

**File**: `/home/harsh/pocketing/pocketing/frontend/src/components/NoteRow.tsx`

**What to do**: Add a thread button with count badge to the note actions. Add `onOpenThread` callback prop.

**Change 1** — Update the import line (line 3) from:
```typescript
import { CheckIcon, CircleIcon, CopyIcon, PinIcon, TrashIcon } from '@/components/Icons';
```
to:
```typescript
import { CheckIcon, CircleIcon, CopyIcon, PinIcon, ThreadIcon, TrashIcon } from '@/components/Icons';
```

**Change 2** — Update the `NoteRowProps` interface (around line 63-70) from:
```typescript
interface NoteRowProps {
  note: Note;
  busy: boolean;
  onUpdate: (note: Note, update: NoteUpdate) => void;
  onDelete: (note: Note) => void;
  dragHandleProps?: Record<string, any>;
  isDragging?: boolean;
}
```
to:
```typescript
interface NoteRowProps {
  note: Note;
  busy: boolean;
  onUpdate: (note: Note, update: NoteUpdate) => void;
  onDelete: (note: Note) => void;
  onOpenThread?: (note: Note) => void;
  dragHandleProps?: Record<string, any>;
  isDragging?: boolean;
}
```

**Change 3** — Update the destructuring (around line 72) from:
```typescript
export function NoteRow({ note, busy, onUpdate, onDelete, dragHandleProps, isDragging }: NoteRowProps) {
```
to:
```typescript
export function NoteRow({ note, busy, onUpdate, onDelete, onOpenThread, dragHandleProps, isDragging }: NoteRowProps) {
```

**Change 4** — In the `note-actions` div (around lines 193-223), add the thread button BEFORE the copy button. Find:
```tsx
      <div className="note-actions">
        <button
          type="button"
          onClick={() => void copyNote()}
```
and replace with:
```tsx
      <div className="note-actions">
        <button
          type="button"
          onClick={() => onOpenThread?.(note)}
          aria-label="Open thread"
          title="Thread"
          className={`note-action-btn${note.thread_count > 0 ? ' has-thread' : ''}`}
        >
          <ThreadIcon size={13} />
          {note.thread_count > 0 && (
            <span className="thread-count-badge">{note.thread_count}</span>
          )}
        </button>
        <button
          type="button"
          onClick={() => void copyNote()}
```

---

## Step 10: Frontend — Update `SortableNoteRow.tsx`

**File**: `/home/harsh/pocketing/pocketing/frontend/src/components/SortableNoteRow.tsx`

**What to do**: Pass through the new `onOpenThread` prop.

**Replace the entire file with**:

```typescript
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { NoteRow } from './NoteRow';
import type { Note, NoteUpdate } from '@/types';

interface SortableNoteRowProps {
  note: Note;
  busy: boolean;
  onUpdate: (note: Note, update: NoteUpdate) => void;
  onDelete: (note: Note) => void;
  onOpenThread?: (note: Note) => void;
}

export function SortableNoteRow(props: SortableNoteRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: props.note.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.8 : 1,
    zIndex: isDragging ? 1 : 0,
    position: 'relative' as const,
  };

  return (
    <div ref={setNodeRef} style={style}>
      <NoteRow {...props} dragHandleProps={{ ...attributes, ...listeners }} isDragging={isDragging} />
    </div>
  );
}
```

**Key change**: Added `onOpenThread?: (note: Note) => void` to the interface. The `{...props}` spread already passes it through to `NoteRow`.

---

## Step 11: Frontend — Create `ThreadView.tsx`

**File**: `/home/harsh/pocketing/pocketing/frontend/src/components/ThreadView.tsx` (NEW FILE)

**Create this file with**:

```typescript
import { useEffect, useRef, useState, type FormEvent } from 'react';

import { threadApi } from '@/api';
import { ArrowLeftIcon, TrashIcon } from '@/components/Icons';
import type { Note, ThreadMessage } from '@/types';

function relativeTime(value: string): string {
  const date = new Date(value);
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return 'now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d`;
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date);
}

interface ThreadViewProps {
  note: Note;
  onBack: () => void;
  onThreadCountChange: (noteId: number, count: number) => void;
}

export function ThreadView({ note, onBack, onThreadCountChange }: ThreadViewProps) {
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    threadApi.list(note.id)
      .then((result) => {
        if (active) {
          setMessages(result);
          onThreadCountChange(note.id, result.length);
        }
      })
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [note.id, onThreadCountChange]);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  async function addMessage(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || sending) return;
    setSending(true);
    setError('');
    try {
      const created = await threadApi.create(note.id, content);
      setMessages((current) => [...current, created]);
      setDraft('');
      onThreadCountChange(note.id, messages.length + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not add message');
    } finally {
      setSending(false);
    }
  }

  async function deleteMessage(messageId: number) {
    setError('');
    try {
      await threadApi.remove(note.id, messageId);
      setMessages((current) => {
        const next = current.filter((m) => m.id !== messageId);
        onThreadCountChange(note.id, next.length);
        return next;
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not delete message');
    }
  }

  // This is called from App.tsx when a WebSocket thread event arrives
  // for this note. We expose addMessageFromWs and removeMessageFromWs
  // via the parent callbacks instead.

  const preview = note.content.length > 80
    ? note.content.slice(0, 80) + '…'
    : note.content;

  return (
    <div className="thread-view">
      {/* Thread Header */}
      <div className="thread-header">
        <button type="button" onClick={onBack} className="thread-back-btn" aria-label="Back to notes">
          <ArrowLeftIcon size={16} />
        </button>
        <div className="thread-header-info">
          <span className="thread-header-label">Thread</span>
          <p className="thread-header-note">{preview}</p>
        </div>
      </div>

      {/* Messages */}
      <div className="thread-messages" ref={listRef}>
        {error && <div className="error-banner">{error}</div>}

        {loading ? (
          <div className="loading-spinner">
            <div className="spinner" />
          </div>
        ) : messages.length === 0 ? (
          <div className="empty-state">
            <p className="empty-state-title">No messages yet</p>
            <p className="empty-state-sub">Add a message to start tracking info for this note</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className="thread-message">
              <div className="thread-message-bubble">
                <p className="thread-message-content">{msg.content}</p>
                <span className="thread-message-time">{relativeTime(msg.created_at)}</span>
              </div>
              <button
                type="button"
                onClick={() => void deleteMessage(msg.id)}
                aria-label="Delete message"
                title="Delete"
                className="thread-message-delete"
              >
                <TrashIcon size={12} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Composer */}
      <div className="thread-composer">
        <form onSubmit={(event) => void addMessage(event)} className="composer-row">
          <input
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Add to thread…"
            maxLength={4000}
            aria-label="New thread message"
            className="composer-input"
          />
          <button
            type="submit"
            disabled={!draft.trim() || sending}
            aria-label="Send"
            className="composer-send"
          >
            {sending ? <span className="spin">↻</span> : 'Send'}
          </button>
        </form>
      </div>
    </div>
  );
}
```

---

## Step 12: Frontend — Update `App.tsx`

**File**: `/home/harsh/pocketing/pocketing/frontend/src/App.tsx`

**What to do**: Add thread view state, handle thread WebSocket events, conditionally render `ThreadView` or notes list.

**Change 1** — Add the ThreadView import. Find (around line 22):
```typescript
import { NoteRow } from '@/components/NoteRow';
```
and add AFTER it:
```typescript
import { ThreadView } from '@/components/ThreadView';
```

**Change 2** — Add `activeThread` state. Find (around line 64):
```typescript
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null);
```
and add AFTER it:
```typescript
  const [activeThread, setActiveThread] = useState<Note | null>(null);
```

**Change 3** — Handle thread WebSocket events. Find the WebSocket `onmessage` handler (around lines 136-143):
```typescript
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as NoteEvent;
        if (event.type === 'note.deleted') {
          setNotes((current) => current.filter((note) => note.id !== event.id));
        } else {
          upsert(event.note);
        }
      };
```
and replace with:
```typescript
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as NoteEvent;
        if (event.type === 'note.deleted') {
          setNotes((current) => current.filter((note) => note.id !== event.id));
          setActiveThread((current) => current?.id === event.id ? null : current);
        } else if (event.type === 'note.created' || event.type === 'note.updated') {
          upsert(event.note);
        } else if (event.type === 'thread.created' || event.type === 'thread.deleted') {
          setNotes((current) =>
            current.map((note) =>
              note.id === event.note_id ? { ...note, thread_count: event.thread_count } : note
            )
          );
        }
      };
```

**Change 4** — Add `handleOpenThread` and `handleThreadCountChange` callbacks. Find the `deleteNote` function (around lines 209-224) and add AFTER it (before `const renderSortableList`):
```typescript
  function handleOpenThread(note: Note) {
    setActiveThread(note);
  }

  const handleThreadCountChange = useCallback((noteId: number, count: number) => {
    setNotes((current) =>
      current.map((note) =>
        note.id === noteId ? { ...note, thread_count: count } : note
      )
    );
  }, []);
```

Also add `useCallback` to the imports at line 1 if not already there (it IS already imported, so no change needed).

**Change 5** — Pass `onOpenThread` to `SortableNoteRow` and `NoteRow`. Find the `renderSortableList` function (around line 226-245). Replace it with:
```typescript
  const renderSortableList = (list: Note[], title: string) => {
    if (list.length === 0) return null;
    return (
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={(e) => handleDragEnd(e, list)}>
        <Section title={title} count={list.length}>
          <SortableContext items={list.map((n) => n.id)} strategy={verticalListSortingStrategy}>
            {list.map((note) => (
              <SortableNoteRow
                key={note.id}
                note={note}
                busy={busyIds.has(note.id)}
                onUpdate={(item, update) => void updateNote(item, update)}
                onDelete={(item) => void deleteNote(item)}
                onOpenThread={handleOpenThread}
              />
            ))}
          </SortableContext>
        </Section>
      </DndContext>
    );
  };
```

**Change 6** — Conditionally render ThreadView or notes list. Find the return statement's `{/* ── Content ── */}` section (around lines 283-343). Replace the entire `<div className="content-area">...</div>` block with:

```tsx
      {/* ── Content ── */}
      {activeThread ? (
        <ThreadView
          note={activeThread}
          onBack={() => setActiveThread(null)}
          onThreadCountChange={handleThreadCountChange}
        />
      ) : (
        <div className="content-area">
          <div className="content-inner">
            {/* Search */}
            <div className="search-bar">
              <SearchIcon size={13} className="search-icon" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search…"
                aria-label="Search notes"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  aria-label="Clear search"
                  className="search-clear"
                >
                  <XIcon size={12} />
                </button>
              )}
            </div>

            {/* Error */}
            {error && <div className="error-banner">{error}</div>}

            {/* Notes */}
            {loading ? (
              <div className="loading-spinner">
                <div className="spinner" />
              </div>
            ) : (
              <>
                {renderSortableList(pinned, 'Pinned')}
                {renderSortableList(inbox, 'Inbox')}
                <Section title="Done" count={done.length}>
                  {done.map((note) => (
                    <NoteRow
                      key={note.id}
                      note={note}
                      busy={busyIds.has(note.id)}
                      onUpdate={(item, update) => void updateNote(item, update)}
                      onDelete={(item) => void deleteNote(item)}
                      onOpenThread={handleOpenThread}
                    />
                  ))}
                </Section>

                {visible.length === 0 && (
                  <div className="empty-state">
                    <div className="empty-state-icon">
                      {search ? <SearchIcon size={20} /> : <CheckIcon size={20} />}
                    </div>
                    <p className="empty-state-title">{search ? 'No results' : 'All clear'}</p>
                    <p className="empty-state-sub">{search ? 'Try a different search' : 'Notes you send will appear here'}</p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
```

**Change 7** — Hide the main composer when viewing a thread. Find the `{/* ── Composer ── */}` section (around line 346-373) and wrap it in a conditional:

Replace:
```tsx
      {/* ── Composer ── */}
      <div className="composer">
```
with:
```tsx
      {/* ── Composer ── */}
      {!activeThread && <div className="composer">
```

And after the composer's closing `</div>` (the one that closes `className="composer"`), add the closing bracket. Find:
```tsx
        </div>
      </div>
```
(the last two closing divs before `</div>` app-shell closing) and replace with:
```tsx
        </div>
      </div>}
```

> **To be precise**: The composer JSX currently is:
> ```tsx
>       <div className="composer">
>         <div className="composer-inner">
>           ...
>         </div>
>       </div>
> ```
> It should become:
> ```tsx
>       {!activeThread && <div className="composer">
>         <div className="composer-inner">
>           ...
>         </div>
>       </div>}
> ```

---

## Step 13: Frontend — Update `index.css`

**File**: `/home/harsh/pocketing/pocketing/frontend/src/index.css`

**What to do**: Add thread-related styles at the end of the file, BEFORE the `/* ─── Responsive ─── */` section (before line 775).

**Insert the following CSS BEFORE the `/* ─── Responsive ─── */` comment:**

```css
/* ─── Thread Count Badge ─── */
.note-action-btn {
  position: relative;
}

.thread-count-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--accent);
  color: var(--text-inverse);
  font-size: 9px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  pointer-events: none;
}

.note-action-btn.has-thread {
  color: var(--text-secondary);
}

/* ─── Thread View ─── */
.thread-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  animation: fadeIn 0.15s ease;
}

.thread-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
  background: var(--bg-primary);
  transition: background var(--transition-theme), border-color var(--transition-theme);
}

.thread-back-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.thread-back-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.thread-header-info {
  min-width: 0;
  flex: 1;
}

.thread-header-label {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  transition: color var(--transition-theme);
}

.thread-header-note {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
  transition: color var(--transition-theme);
}

.thread-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.thread-message {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
  animation: fadeIn 0.15s ease both;
}

.thread-message-bubble {
  flex: 1;
  min-width: 0;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid var(--border-secondary);
  background: var(--bg-secondary);
  border-top-left-radius: 2px;
  transition: border-color var(--transition-theme), background var(--transition-theme);
}

.thread-message-content {
  font-size: 14px;
  line-height: 1.55;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  transition: color var(--transition-theme);
}

.thread-message-time {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-tertiary);
  transition: color var(--transition-theme);
}

.thread-message-delete {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--text-quaternary);
  opacity: 0;
  margin-top: 8px;
  transition: color var(--transition-fast), background var(--transition-fast), opacity var(--transition-fast);
}

.thread-message:hover .thread-message-delete {
  opacity: 1;
}

.thread-message-delete:hover {
  background: var(--danger-muted);
  color: var(--danger);
}

.thread-composer {
  flex-shrink: 0;
  border-top: 1px solid var(--border-primary);
  padding: 14px 20px;
  background: var(--bg-primary);
  transition: background var(--transition-theme), border-color var(--transition-theme);
}

@media (hover: none) {
  .thread-message-delete {
    opacity: 1;
  }
}
```

Also add to the responsive section (inside the `@media (min-width: 640px)` block) these additional rules:

Find the existing responsive block:
```css
@media (min-width: 640px) {
  .app-header {
    padding: 18px 32px;
  }

  .content-area {
    padding: 0 32px;
  }

  .composer {
    padding: 16px 32px;
  }
}
```

Replace it with:
```css
@media (min-width: 640px) {
  .app-header {
    padding: 18px 32px;
  }

  .content-area {
    padding: 0 32px;
  }

  .composer {
    padding: 16px 32px;
  }

  .thread-header {
    padding: 16px 32px;
  }

  .thread-messages {
    padding: 20px 32px;
  }

  .thread-composer {
    padding: 16px 32px;
  }
}
```

---

## Verification Plan

After implementing all 13 steps, run these checks:

### 1. Start the backend
```bash
cd /home/harsh/pocketing/pocketing/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### 2. Test API endpoints with curl
```bash
# Create a test note
curl -s -X POST http://localhost:8000/api/notes \
  -H "Content-Type: application/json" \
  -d '{"content": "Test note for threads"}' | python3 -m json.tool

# List notes — verify thread_count: 0 is present
curl -s http://localhost:8000/api/notes | python3 -m json.tool

# Add a thread message (replace 1 with actual note id)
curl -s -X POST http://localhost:8000/api/notes/1/thread \
  -H "Content-Type: application/json" \
  -d '{"content": "First thread reply"}' | python3 -m json.tool

# List thread messages
curl -s http://localhost:8000/api/notes/1/thread | python3 -m json.tool

# List notes again — verify thread_count: 1
curl -s http://localhost:8000/api/notes | python3 -m json.tool

# Delete the note — should cascade delete thread messages
curl -s -X DELETE http://localhost:8000/api/notes/1
```

### 3. Build and test frontend
```bash
cd /home/harsh/pocketing/pocketing/frontend
npm run dev
```

### 4. Manual UI verification
- Open the app in browser
- Verify each note shows a 💬 thread icon in actions (on hover)
- Create a note, click its thread icon → should open full-page thread view
- Verify back button returns to notes list
- Add thread messages → count badge should appear on the note
- Delete a thread message → count should update
- Delete the parent note → should return to notes list (if viewing its thread)
