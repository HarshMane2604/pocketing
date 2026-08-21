"""SQLite models."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="web", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    thread_messages: Mapped[list["ThreadMessage"]] = relationship(
        "ThreadMessage", back_populates="note", cascade="all, delete-orphan", passive_deletes=True
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment",
        back_populates="note",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="Attachment.note_id",
    )


class ThreadMessage(Base):
    __tablename__ = "thread_messages"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    note: Mapped["Note"] = relationship("Note", back_populates="thread_messages")
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment",
        back_populates="thread_message",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="Attachment.thread_message_id",
    )


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint(
            "(note_id IS NOT NULL AND thread_message_id IS NULL) OR "
            "(note_id IS NULL AND thread_message_id IS NOT NULL)",
            name="ck_attachment_owner",
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    thread_message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("thread_messages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    note: Mapped["Note | None"] = relationship("Note", back_populates="attachments", foreign_keys=[note_id])
    thread_message: Mapped["ThreadMessage | None"] = relationship(
        "ThreadMessage", back_populates="attachments", foreign_keys=[thread_message_id]
    )

    @property
    def url(self) -> str:
        return f"/api/files/{self.storage_key}"


class AppSetting(Base):
    """Tiny key/value store for bridge state such as the paired Telegram chat."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
