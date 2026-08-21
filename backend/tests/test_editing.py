import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from app.api import update_note
from app.models import Note
from app.schemas import NoteUpdate
from app.service import NOTE_EDIT_WINDOW_MINUTES, note_can_edit, note_editable_until
from app.telegram import TelegramBridge, TelegramMessageRef


class EditingWindowTests(unittest.TestCase):
    def test_recent_web_note_is_editable(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
        note = Note(
            content="hello",
            source="web",
            created_at=now - timedelta(minutes=14, seconds=59),
        )

        self.assertTrue(note_can_edit(note, now))
        self.assertEqual(
            note_editable_until(note),
            note.created_at + timedelta(minutes=NOTE_EDIT_WINDOW_MINUTES),
        )

    def test_web_note_expires_at_fifteen_minutes(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
        note = Note(
            content="hello",
            source="web",
            created_at=now - timedelta(minutes=15),
        )

        self.assertFalse(note_can_edit(note, now))

    def test_telegram_authored_note_is_not_editable_from_pocketing(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
        note = Note(
            content="hello",
            source="telegram",
            created_at=now - timedelta(minutes=1),
        )

        self.assertFalse(note_can_edit(note, now))

    def test_naive_sqlite_timestamp_is_treated_as_utc(self) -> None:
        note = Note(
            content="hello",
            source="web",
            created_at=datetime(2026, 8, 21, 12, 0),
        )

        self.assertEqual(note_editable_until(note).tzinfo, timezone.utc)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        self.requests.append((url, json))
        return self.response


class TelegramEditingTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_returns_reference_needed_for_editing(self) -> None:
        bridge = TelegramBridge()
        bridge.token = "test-token"
        bridge.active_chat_id = "123"
        client = _FakeClient(
            _FakeResponse(
                {
                    "ok": True,
                    "result": {"message_id": 456, "chat": {"id": 123}},
                }
            )
        )

        with patch("app.telegram.httpx.AsyncClient", return_value=client):
            result = await bridge.send_message("hello")

        self.assertEqual(result, TelegramMessageRef(chat_id="123", message_id=456))
        self.assertEqual(client.requests[0][1], {"chat_id": "123", "text": "hello"})

    async def test_edit_message_targets_the_original_telegram_message(self) -> None:
        bridge = TelegramBridge()
        bridge.token = "test-token"
        client = _FakeClient(_FakeResponse({"ok": True, "result": {"message_id": 456}}))

        with patch("app.telegram.httpx.AsyncClient", return_value=client):
            updated = await bridge.edit_message("123", 456, "updated")

        self.assertTrue(updated)
        self.assertTrue(client.requests[0][0].endswith("/editMessageText"))
        self.assertEqual(
            client.requests[0][1],
            {"chat_id": "123", "message_id": 456, "text": "updated"},
        )


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, *_args: object, **_kwargs: object) -> None:
        return None


def _web_note(created_at: datetime) -> Note:
    return Note(
        id=1,
        content="original",
        structured_content=None,
        created_at=created_at,
        is_pinned=False,
        is_done=False,
        source="web",
        priority=0,
        telegram_chat_id="123",
        telegram_message_id=456,
        attachments=[],
    )


class NoteUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_content_edit_is_rejected(self) -> None:
        note = _web_note(datetime.now(timezone.utc) - timedelta(minutes=16))
        session = _FakeSession()

        with patch("app.api.get_note_or_404", AsyncMock(return_value=note)):
            with self.assertRaises(HTTPException) as raised:
                await update_note(1, NoteUpdate(content="updated"), session)  # type: ignore[arg-type]

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(note.content, "original")
        self.assertEqual(session.commits, 0)

    async def test_telegram_failure_keeps_local_note_unchanged(self) -> None:
        note = _web_note(datetime.now(timezone.utc) - timedelta(minutes=1))
        session = _FakeSession()

        with (
            patch("app.api.get_note_or_404", AsyncMock(return_value=note)),
            patch("app.api.telegram_bridge.edit_message", AsyncMock(return_value=False)),
        ):
            with self.assertRaises(HTTPException) as raised:
                await update_note(1, NoteUpdate(content="updated"), session)  # type: ignore[arg-type]

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(note.content, "original")
        self.assertEqual(session.commits, 0)

    async def test_successful_edit_updates_telegram_and_local_note(self) -> None:
        note = _web_note(datetime.now(timezone.utc) - timedelta(minutes=1))
        session = _FakeSession()
        telegram_edit = AsyncMock(return_value=True)

        with (
            patch("app.api.get_note_or_404", AsyncMock(return_value=note)),
            patch("app.api.telegram_bridge.edit_message", telegram_edit),
            patch("app.api.get_thread_count", AsyncMock(return_value=0)),
            patch("app.api.connections.broadcast", AsyncMock()),
        ):
            response = await update_note(  # type: ignore[arg-type]
                1,
                NoteUpdate(content="updated"),
                session,
            )

        telegram_edit.assert_awaited_once_with("123", 456, "updated")
        self.assertEqual(note.content, "updated")
        self.assertEqual(response["content"], "updated")
        self.assertEqual(session.commits, 1)


if __name__ == "__main__":
    unittest.main()
