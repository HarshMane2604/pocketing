"""API request and response types."""

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


MAX_STRUCTURED_CONTENT_BYTES = 200_000
ALLOWED_NODE_TYPES = {
    "doc",
    "paragraph",
    "text",
    "heading",
    "bulletList",
    "orderedList",
    "listItem",
    "taskList",
    "taskItem",
    "blockquote",
    "codeBlock",
    "hardBreak",
    "horizontalRule",
}
ALLOWED_MARK_TYPES = {"bold", "italic", "underline", "strike", "code", "link"}
ALLOWED_ALIGNMENTS = {"left", "center", "right", None}


def validate_structured_content(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate the bounded subset of Tiptap JSON that Pocketing supports."""
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("type") != "doc":
        raise ValueError("Structured content must be a Tiptap document")
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > MAX_STRUCTURED_CONTENT_BYTES:
        raise ValueError("Structured content is too large")

    node_count = 0

    def visit(node: object, depth: int = 0) -> None:
        nonlocal node_count
        if depth > 40 or not isinstance(node, dict):
            raise ValueError("Structured content is malformed")
        node_count += 1
        if node_count > 10_000:
            raise ValueError("Structured content has too many nodes")

        node_type = node.get("type")
        if node_type not in ALLOWED_NODE_TYPES:
            raise ValueError(f"Unsupported rich-text node: {node_type}")

        attrs = node.get("attrs") or {}
        if not isinstance(attrs, dict):
            raise ValueError("Structured content attributes are malformed")
        if node_type == "heading" and attrs.get("level") not in {1, 2, 3}:
            raise ValueError("Only H1, H2, and H3 headings are supported")
        if attrs.get("textAlign") not in ALLOWED_ALIGNMENTS:
            raise ValueError("Unsupported text alignment")
        if node_type == "taskItem" and "checked" in attrs and not isinstance(attrs["checked"], bool):
            raise ValueError("Checklist state must be a boolean")

        marks = node.get("marks") or []
        if not isinstance(marks, list):
            raise ValueError("Structured content marks are malformed")
        for mark in marks:
            if not isinstance(mark, dict) or mark.get("type") not in ALLOWED_MARK_TYPES:
                raise ValueError("Unsupported rich-text mark")
            if mark.get("type") == "link":
                href = str((mark.get("attrs") or {}).get("href") or "")
                parsed = urlparse(href)
                if parsed.scheme.lower() not in {"http", "https", "mailto"}:
                    raise ValueError("Links must use http, https, or mailto")

        children = node.get("content") or []
        if not isinstance(children, list):
            raise ValueError("Structured content children are malformed")
        for child in children:
            visit(child, depth + 1)

    visit(value)
    return value


def parse_stored_structured_content(value: object) -> dict[str, Any] | None:
    if value is None or isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        return None


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
    structured_content: dict[str, Any] | None = None

    @field_validator("content")
    @classmethod
    def strip_optional_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Note cannot be empty")
        return value

    @field_validator("structured_content")
    @classmethod
    def validate_document(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_structured_content(value)


class ReorderRequest(BaseModel):
    note_ids: list[int]


class AttachmentResponse(BaseModel):
    id: int
    filename: str
    content_type: str
    size_bytes: int
    url: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")


class NoteResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    is_pinned: bool
    is_done: bool
    source: str
    priority: int
    thread_count: int = 0
    attachments: list[AttachmentResponse] = []
    structured_content: dict[str, Any] | None = None
    can_edit: bool = False
    editable_until: datetime | None = None
    telegram_sync_available: bool = False

    model_config = ConfigDict(from_attributes=True)

    @field_validator("structured_content", mode="before")
    @classmethod
    def parse_document(cls, value: object) -> dict[str, Any] | None:
        return parse_stored_structured_content(value)

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
    attachments: list[AttachmentResponse] = []
    structured_content: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("structured_content", mode="before")
    @classmethod
    def parse_document(cls, value: object) -> dict[str, Any] | None:
        return parse_stored_structured_content(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")


class FileSearchResult(BaseModel):
    """Attachment with parent context for the files management view."""

    id: int
    filename: str
    content_type: str
    size_bytes: int
    url: str
    created_at: datetime
    parent_type: str  # "note" or "thread"
    parent_id: int
    parent_content: str  # truncated snippet

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
