"""Minimal Telegram long-polling bridge."""

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.database import SessionLocal
from app.service import create_note, get_setting, set_setting

logger = logging.getLogger(__name__)
TELEGRAM_CHAT_SETTING = "telegram_chat_id"


class TelegramBridge:
    def __init__(self) -> None:
        settings = get_settings()
        self.token = settings.telegram_bot_token.strip()
        self.allowed_chat_id = settings.telegram_allowed_chat_id.strip()
        self.active_chat_id = self.allowed_chat_id
        self.task: asyncio.Task[None] | None = None
        self.last_error: str | None = None
        self.last_message_at: datetime | None = None
        self.last_sent_at: datetime | None = None

    def status(self) -> dict[str, object]:
        return {
            "configured": bool(self.token),
            "running": self.task is not None and not self.task.done(),
            "chat_restricted": bool(self.allowed_chat_id),
            "target_ready": bool(self.active_chat_id),
            "last_error": self.last_error,
            "last_message_at": self.last_message_at,
            "last_sent_at": self.last_sent_at,
        }

    @staticmethod
    def safe_error(error: Exception) -> str:
        # Never expose or log the request URL because it contains the bot token.
        if isinstance(error, httpx.HTTPStatusError):
            return f"Telegram HTTP {error.response.status_code}"
        return type(error).__name__

    async def initialize(self) -> None:
        """Load an automatically paired chat from SQLite after tables exist."""
        if self.active_chat_id:
            return
        async with SessionLocal() as session:
            self.active_chat_id = await get_setting(session, TELEGRAM_CHAT_SETTING) or ""

    def start(self) -> None:
        if self.token and self.task is None:
            self.task = asyncio.create_task(self.poll(), name="telegram-inbox")
            logger.info("Telegram capture enabled")
        elif not self.token:
            logger.info("Telegram capture disabled: TELEGRAM_BOT_TOKEN is empty")

    async def stop(self) -> None:
        if self.task is None:
            return
        self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task
        self.task = None

    async def poll(self) -> None:
        offset: int | None = None
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        async with httpx.AsyncClient(timeout=httpx.Timeout(35)) as client:
            while True:
                try:
                    params: dict[str, Any] = {
                        "timeout": 25,
                        "allowed_updates": '["message"]',
                    }
                    if offset is not None:
                        params["offset"] = offset
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    if not payload.get("ok"):
                        raise RuntimeError("Telegram returned an unsuccessful response")
                    self.last_error = None
                    for update in payload.get("result", []):
                        offset = int(update["update_id"]) + 1
                        await self.capture(update)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    self.last_error = self.safe_error(error)
                    logger.warning("Telegram polling failed; retrying: %s", self.last_error)
                    await asyncio.sleep(3)

    async def capture(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", ""))
        if self.allowed_chat_id and chat_id != self.allowed_chat_id:
            logger.warning("Ignored Telegram message from an unapproved chat")
            return
        if self.active_chat_id and chat_id != self.active_chat_id:
            logger.warning("Ignored Telegram message from a chat other than the paired chat")
            return

        async with SessionLocal() as session:
            if not self.active_chat_id:
                self.active_chat_id = chat_id
                await set_setting(session, TELEGRAM_CHAT_SETTING, chat_id)
                self.last_error = None
                logger.info("Telegram chat paired automatically")

            content = (message.get("text") or message.get("caption") or "").strip()
            # Commands can pair the chat, but are not stored as notes.
            if not content or content.startswith("/"):
                return
            date_val = message.get("date")
            created_at = (
                datetime.fromtimestamp(date_val, tz=timezone.utc) if date_val else None
            )
            await create_note(
                session, content, source="telegram", created_at=created_at
            )
        self.last_message_at = datetime.now(timezone.utc)

    async def send_message(self, content: str) -> bool:
        """Send a browser-created note to the paired Telegram chat."""
        if not self.token:
            self.last_error = "Telegram is not configured"
            return False
        if not self.active_chat_id:
            self.last_error = "Send the bot a message once to pair this inbox"
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
                response = await client.post(
                    url,
                    json={"chat_id": self.active_chat_id, "text": content},
                )
                response.raise_for_status()
                if not response.json().get("ok"):
                    raise RuntimeError("Telegram returned an unsuccessful response")
            self.last_error = None
            self.last_sent_at = datetime.now(timezone.utc)
            return True
        except Exception as error:
            self.last_error = self.safe_error(error)
            logger.warning("Telegram send failed: %s", self.last_error)
            return False


telegram_bridge = TelegramBridge()
