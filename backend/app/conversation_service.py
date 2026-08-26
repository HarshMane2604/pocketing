import json
from app.database import SessionLocal
from app.models import Conversation, ConversationMessage
from sqlalchemy import select
from datetime import timedelta, datetime
CONVERSATION_TIMEOUT=timedelta(minutes=10)

async def get_or_create_conversation(chat_id: str) -> int:
    async with SessionLocal() as session:
        # Find the most recent conversation for this chat
        result = await session.execute(
            select(Conversation)
            .where(Conversation.chat_id == chat_id)
            .order_by(Conversation.last_activate_at.desc())
            .limit(1)
        )  
        conv = result.scalars().first()
        now = datetime.utcnow()
        if conv and (now - conv.last_activate_at) < CONVERSATION_TIMEOUT:
            # still active - reuse it 
            conv.last_activate_at = now
            await session.commit()
            return conv.id
        else:
            # Expired or doesn't exist - create new
             conv = Conversation(chat_id=chat_id)
             session.add(conv)
             await session.commit()
             await session.refresh(conv)
             return conv.id


async def reset_conversation(chat_id: str) -> None:
    """Force reset the conversation for this chat by setting last_activate_at to 1970."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.chat_id == chat_id)
            .order_by(Conversation.last_activate_at.desc())
            .limit(1)
        )
        conv = result.scalars().first()
        if conv:
            conv.last_activate_at = datetime(1970, 1, 1)
            await session.commit()


async def touch_conversation(conversation_id: int) -> None:
    """Bump last_activate_at to now. Call at the END of an agent run
    so the timeout window starts from when Qwen *finished*, not when
    the user's message arrived."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalars().first()
        if conv:
            conv.last_activate_at = datetime.utcnow()
            await session.commit()


async def load_conversation_messages(Conversation_id: int) -> list[dict]:
    """ Load all messages for a conversation, formatted for Ollama"""
    async with SessionLocal() as session:
        result = await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == Conversation_id)
            .order_by(ConversationMessage.created_at)
        )
        rows = result.scalars().all()

        messages = []
        for row in rows:
            msg={"role": row.role, "content": row.content}
            if row.tool_calls_json:
                msg["tool_calls"] = json.loads(row.tool_calls_json)
            if row.tool_call_id:
                msg["tool_call_id"] = row.tool_call_id
            messages.append(msg)
        
        return messages
    
async def save_message(
    conversation_id: int,
    role: str,
    content: str,
    tool_calls: list | None = None,
    tool_call_id: str | None = None
) -> None:
    async with SessionLocal() as session:
        msg = ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls_json = json.dumps(tool_calls) if tool_calls else None,
            tool_call_id = tool_call_id
        )
        session.add(msg)

        await session.commit()

MAX_HISTORY_MESSAGES = 20  # Keep last 10 turns
MAX_CONTENT_CHARS = 800  # Truncate older contents to save context tokens

def trim_conversation_history(messages: list[dict]) -> list[dict]:
    """Keep recent messages and compress older long messages to fit context limits."""
    if not messages:
        return messages

    system = messages[:1]
    other_messages = messages[1:]

    # Slice the last MAX_HISTORY_MESSAGES
    if len(other_messages) > MAX_HISTORY_MESSAGES:
        other_messages = other_messages[-MAX_HISTORY_MESSAGES:]

    # Truncate content of any message (user, assistant, tool) not in the last 4 messages
    for i, msg in enumerate(other_messages):
        if i < len(other_messages) - 4:
            content = msg.get("content")
            if content and isinstance(content, str) and len(content) > MAX_CONTENT_CHARS:
                # Make a copy to avoid mutating database-bound models directly
                msg = dict(msg)
                msg["content"] = content[:MAX_CONTENT_CHARS] + "... [truncated for context size]"
                other_messages[i] = msg

            # Also truncate tool calls JSON if it exists in assistant messages
            if "tool_calls" in msg:
                msg = dict(msg)
                # Deep copy tool calls to avoid mutating original
                import copy
                msg["tool_calls"] = copy.deepcopy(msg["tool_calls"])
                for tc in msg["tool_calls"]:
                    if "function" in tc and "arguments" in tc["function"]:
                        args = tc["function"]["arguments"]
                        if isinstance(args, dict):
                            for k, v in args.items():
                                if isinstance(v, str) and len(v) > MAX_CONTENT_CHARS:
                                    args[k] = v[:MAX_CONTENT_CHARS] + "... [truncated]"
                other_messages[i] = msg

    return system + other_messages
