"""Minimal Telegram long-polling bridge."""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.database import SessionLocal
from app.models import Attachment
from app.service import create_note, get_setting, save_file_data, set_setting

from pocketing_logging.logger import get_telegram_logger

logger = get_telegram_logger()
TELEGRAM_CHAT_SETTING = "telegram_chat_id"


@dataclass(frozen=True)
class TelegramMessageRef:
    chat_id: str
    message_id: int


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
        self.active_ai_tasks: dict[str, asyncio.Task[None]] = {}

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

    async def _download_file(self, client: httpx.AsyncClient, file_id: str) -> tuple[bytes, str] | None:
        """Fetch a file from Telegram using file_id. Returns (data, file_path) or None on error."""
        try:
            get_url = f"https://api.telegram.org/bot{self.token}/getFile"
            resp = await client.get(get_url, params={"file_id": file_id})
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                return None
            file_path = result["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            file_resp = await client.get(download_url)
            file_resp.raise_for_status()
            return file_resp.content, file_path
        except Exception as err:
            logger.warning("Telegram file download failed: %s", type(err).__name__)
            return None

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

            # ── Handle explicit reset/revoke commands ──────────────────────
            if content.lower() in ("/reset", "/revoke"):
                # Cancel ongoing AI task if running
                if chat_id in self.active_ai_tasks:
                    self.active_ai_tasks[chat_id].cancel()
                    logger.info("Cancelled ongoing AI task for chat_id %s", chat_id)
                
                # Reset conversation context in DB
                from app.conversation_service import reset_conversation
                await reset_conversation(chat_id)
                
                await self.send_message("🔄 Conversation reset. Started a fresh session.")
                return

            # Commands can pair the chat, but are not stored as notes.
            if content.startswith("/") and not content.lower().endswith("/ai"):
                return

            # (Note: AI flow moved to the end of the method to capture media first)

            # ── Detect incoming media ──────────────────────────────────────────
            # Each entry: (file_id, filename, content_type)
            media_items: list[tuple[str, str, str]] = []

            if doc := message.get("document"):
                mime = doc.get("mime_type") or "application/octet-stream"
                media_items.append((doc["file_id"], doc.get("file_name") or "document", mime))

            elif photos := message.get("photo"):
                # Telegram sends multiple resolutions; last = largest
                photo = photos[-1]
                media_items.append((photo["file_id"], "photo.jpg", "image/jpeg"))

            elif vid := message.get("video"):
                mime = vid.get("mime_type") or "video/mp4"
                ext = ".mp4" if "mp4" in mime else ".mkv"
                media_items.append((vid["file_id"], f"video{ext}", mime))

            elif audio := message.get("audio"):
                mime = audio.get("mime_type") or "audio/mpeg"
                fname = audio.get("file_name") or "audio.mp3"
                media_items.append((audio["file_id"], fname, mime))

            elif voice := message.get("voice"):
                media_items.append((voice["file_id"], "voice.ogg", "audio/ogg"))

            # Skip if there's nothing at all (no text, no media)
            if not content and not media_items:
                return

            # Use a fallback content if only files were sent
            final_content = content or "📎 Attachment"

            # Download and save each media item, build Attachment objects
            pre_attachments: list[Attachment] = []
            if media_items:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60)) as client:
                    for file_id, filename, mime in media_items:
                        result = await self._download_file(client, file_id)
                        if result is None:
                            continue
                        data, _file_path = result
                        try:
                            storage_key, content_type, size = save_file_data(filename, mime, data)
                            att = Attachment(
                                filename=filename,
                                storage_key=storage_key,
                                content_type=content_type,
                                size_bytes=size,
                            )
                            pre_attachments.append(att)
                        except ValueError as err:
                            logger.warning("Skipping Telegram file: %s", err)

            date_val = message.get("date")
            created_at = (
                datetime.fromtimestamp(date_val, tz=timezone.utc) if date_val else None
            )
            is_ai_query = content.lower().endswith("/ai")
            
            # Save the note if it's not an AI query, OR if it has attachments (so the AI can access them)
            if not (is_ai_query and not pre_attachments):
                await create_note(
                    session,
                    final_content,
                    source="telegram",
                    created_at=created_at,
                    pre_attachments=pre_attachments or None,
                    telegram_chat_id=chat_id,
                    telegram_message_id=(
                        int(message["message_id"]) if message.get("message_id") is not None else None
                    ),
                )

            # ── suffix /ai → Qwen AI agent ────────────────────────────────────
            if is_ai_query:
                user_query = content[:-3].strip()  # strip trailing " /ai"
                if not user_query:
                    await self.send_message(
                        "🤖 Usage: <your question> /ai\n"
                        "Example: find my Redis note /ai"
                    )
                    return

                # If there were attachments, append a system note so Qwen knows they exist in Pocketing!
                if pre_attachments:
                    filenames = ", ".join([att.filename for att in pre_attachments])
                    user_query += f"\n\n[System Note: The user attached the following file(s) which have been saved to Pocketing: {filenames}. You can use search_files or get_file_info to find and read them.]"

                # Send an animated face (eyebrows + eyes) and cycle it while the agent works
                FACE_NEUTRAL = "<pre> ⌒   ⌒ \n( ◉ ◉ )\n  ...</pre>"
                FACE_BLINK   = "<pre> ⌒   ⌒ \n( ˉ  ˉ )\n  ...</pre>"
                FACE_LEFT    = "<pre> ⌒   ⌒ \n(◉   ◉ )\n...</pre>"
                FACE_RIGHT   = "<pre> ⌒   ⌒ \n( ◉   ◉)\n    ...</pre>"
                FACE_FURROW  = "<pre>  ╲  ╱  \n( ◉  ◉ )\n  ...</pre>"

                thinking_ref = await self.send_message(FACE_NEUTRAL, parse_mode="HTML")

                async def _animate_thinking():
                    if not thinking_ref:
                        return
                    # Weighted so it mostly rests neutral, occasionally blinks/looks/furrows
                    frames = [
                        FACE_NEUTRAL, FACE_NEUTRAL, FACE_BLINK,
                        FACE_NEUTRAL, FACE_LEFT, FACE_NEUTRAL,
                        FACE_FURROW, FACE_NEUTRAL, FACE_RIGHT,
                    ]
                    i = 0
                    while True:
                        await asyncio.sleep(1.0)
                        i = (i + 1) % len(frames)
                        await self.edit_message(
                            thinking_ref.chat_id,
                            thinking_ref.message_id,
                            frames[i],
                            parse_mode="HTML",
                        )

                animation_task = asyncio.create_task(_animate_thinking())

                async def _run_agent_task():
                    from mcp_pocketing.ai_client import run_ai_agent
                    try:
                        ai_response = await run_ai_agent(user_query, chat_id=chat_id)
                        
                        # Stop animation first to prevent it overwriting the final answer
                        animation_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await animation_task

                        if thinking_ref:
                            await self.edit_message(
                                thinking_ref.chat_id,
                                thinking_ref.message_id,
                                ai_response,
                            )
                        else:
                            await self.send_message(ai_response)
                    except asyncio.CancelledError:
                        animation_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await animation_task
                        if thinking_ref:
                            await self.edit_message(
                                thinking_ref.chat_id,
                                thinking_ref.message_id,
                                "🛑 AI process stopped by user.",
                            )
                        else:
                            await self.send_message("🛑 AI process stopped.")
                        raise
                    except Exception as exc:
                        animation_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await animation_task
                        err_msg = f"⚠️ AI error: {type(exc).__name__}: {exc}"
                        if thinking_ref:
                            await self.edit_message(
                                thinking_ref.chat_id,
                                thinking_ref.message_id,
                                err_msg,
                            )
                        else:
                            await self.send_message(err_msg)
                    finally:
                        animation_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await animation_task
                        self.active_ai_tasks.pop(chat_id, None)

                # Cancel previous active AI task for this chat if any, to avoid queueing
                if chat_id in self.active_ai_tasks:
                    self.active_ai_tasks[chat_id].cancel()
                    with suppress(asyncio.CancelledError):
                        await self.active_ai_tasks[chat_id]

                ai_task = asyncio.create_task(_run_agent_task())
                self.active_ai_tasks[chat_id] = ai_task
                return
        self.last_message_at = datetime.now(timezone.utc)

    async def send_message(self, content: str, parse_mode: str | None = None) -> TelegramMessageRef | None:
        """Send a browser-created note to the paired Telegram chat."""
        if not self.token:
            self.last_error = "Telegram is not configured"
            return None
        if not self.active_chat_id:
            self.last_error = "Send the bot a message once to pair this inbox"
            return None

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
                payload = {"chat_id": self.active_chat_id, "text": content}
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                response = await client.post(
                    url,
                    json=payload,
                )
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok"):
                    raise RuntimeError("Telegram returned an unsuccessful response")
                result = payload.get("result") or {}
                message_id = result.get("message_id")
                result_chat_id = (result.get("chat") or {}).get("id")
                if message_id is None or result_chat_id is None:
                    raise RuntimeError("Telegram did not return a message reference")
            self.last_error = None
            self.last_sent_at = datetime.now(timezone.utc)
            return TelegramMessageRef(
                chat_id=str(result_chat_id),
                message_id=int(message_id),
            )
        except Exception as error:
            self.last_error = self.safe_error(error)
            logger.warning("Telegram send failed: %s", self.last_error)
            return None

    async def edit_message(self, chat_id: str, message_id: int, content: str, parse_mode: str | None = None) -> bool:
        """Edit a text message previously sent by this bot."""
        if not self.token:
            self.last_error = "Telegram is not configured"
            return False

        url = f"https://api.telegram.org/bot{self.token}/editMessageText"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
                payload = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": content,
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                response = await client.post(
                    url,
                    json=payload,
                )
                response.raise_for_status()
                if not response.json().get("ok"):
                    raise RuntimeError("Telegram returned an unsuccessful response")
            self.last_error = None
            self.last_sent_at = datetime.now(timezone.utc)
            return True
        except httpx.HTTPStatusError as error:
            self.last_error = f"Telegram HTTP {error.response.status_code}: {error.response.text}"
            logger.warning("Telegram edit failed: %s", self.last_error)
            return False
        except Exception as error:
            self.last_error = self.safe_error(error)
            logger.warning("Telegram edit failed: %s", self.last_error)
            return False

    async def send_file(
        self,
        file_path: str | Path,
        filename: str,
        caption: str | None = None,
    ) -> bool:
        """Send a file to the paired Telegram chat using sendDocument.

        Args:
            file_path: Absolute path to the file on disk.
            filename: The display filename for Telegram.
            caption: Optional text caption (max 1024 chars for Telegram).
        """
        if not self.token:
            return False
        if not self.active_chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        path = Path(file_path)
        if not path.is_file():
            logger.warning("Telegram send_file: file not found: %s", path)
            return False

        try:
            # Telegram Bot API: max 50 MB for sendDocument (matches our limit)
            async with httpx.AsyncClient(timeout=httpx.Timeout(60)) as client:
                with open(path, "rb") as f:
                    files_payload = {"document": (filename, f)}
                    data_payload: dict[str, str] = {"chat_id": self.active_chat_id}
                    if caption:
                        data_payload["caption"] = caption[:1024]
                    response = await client.post(
                        url,
                        data=data_payload,
                        files=files_payload,
                    )
                    response.raise_for_status()
                    if not response.json().get("ok"):
                        raise RuntimeError("Telegram returned an unsuccessful response")
            self.last_error = None
            self.last_sent_at = datetime.now(timezone.utc)
            return True
        except Exception as error:
            self.last_error = self.safe_error(error)
            logger.warning("Telegram send_file failed: %s", self.last_error)
            return False


telegram_bridge = TelegramBridge()
