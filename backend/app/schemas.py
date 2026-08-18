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
