# Implementing Conversation Context for Pocketing AI

## TL;DR

**No, you don't need a vector DB.** Your use case is short-term conversational memory (resolving "it", "that file", "send it to me"). That's just keeping the last N messages in a list and feeding them to Qwen. A vector DB is for *long-term semantic retrieval* across thousands of past conversations — overkill right now.

---

## What You Have Today

```
User sends "find my resume /ai"
    ↓
telegram.py strips "/ai", calls run_ai_agent(user_query, chat_id)
    ↓
ai_client.py builds a FRESH messages list every time:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},   ← just THIS message
    ]
    ↓
Runs the tool-calling loop (up to 10 iterations)
    ↓
Saves to ai_conversations table (flat: user_query + ai_response)
    ↓
Returns answer string
```

**The problem:** Every call to `run_ai_agent()` starts with a blank slate. Qwen has zero memory of anything you said before.

---

## What You Need to Change

There are **3 layers** to this:

### Layer 1: Store Conversations Properly (Database)
### Layer 2: Load History Before Calling Qwen (ai_client.py)  
### Layer 3: Manage Context Window Size (so you don't overflow Qwen)

---

## Layer 1: Database — Store Full Conversation Turns

### The Problem with `ai_conversations` Today

Your current [AiConversation](file:///home/harsh/pocketing/pocketing/backend/app/models.py#L115-L129) model stores flat rows:

```
| id | chat_id | user_query | ai_response | created_at |
```

This is a log, not a conversation. There's no concept of "these 5 exchanges belong to the same conversation session."

### What You Need

You need **two models**: a `Conversation` (the session) and `ConversationMessage` (each turn within it).

```python
# In app/models.py

class Conversation(Base):
    """A conversation session between a user and the AI."""
    __tablename__ = "conversations"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    messages: Mapped[list["ConversationMessage"]] = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )


class ConversationMessage(Base):
    """A single message in a conversation."""
    __tablename__ = "conversation_messages"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user", "assistant", "tool"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls_json: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON blob
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True) # for tool results
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
```

### Why This Shape?

| Field | Purpose |
|---|---|
| `role` | Maps directly to Ollama's message format: `"user"`, `"assistant"`, `"tool"` |
| `content` | The text content of the message |
| `tool_calls_json` | When Qwen calls tools, store the full `tool_calls` array as JSON. You need this to replay the conversation correctly. |
| `tool_call_id` | For `role="tool"` messages — links the result back to the tool call. Ollama requires this. |
| `conversation_id` | Groups messages into a session |
| `last_active_at` | On the `Conversation` — this is how you'll decide if a conversation is "still active" or expired |

### Migration

Since you're on SQLite with `create_all()`, these are new tables so they'll just get created. No migration needed. Keep the old `ai_conversations` table around — it's not hurting anything.

---

## Layer 2: Load History Before Calling Qwen

This is where the actual magic happens. Here's the flow:

### Step 1: Resolve the Active Conversation

When a `/ai` message comes in for `chat_id`, look up the most recent `Conversation` for that chat. If it's recent enough (e.g., within the last 30 minutes), reuse it. Otherwise, create a new one.

```python
# In ai_client.py or a new conversation_service.py

from datetime import timedelta

CONVERSATION_TIMEOUT = timedelta(minutes=30)

async def get_or_create_conversation(chat_id: str) -> int:
    """Returns the conversation_id to use."""
    async with SessionLocal() as session:
        # Find the most recent conversation for this chat
        result = await session.execute(
            select(Conversation)
            .where(Conversation.chat_id == chat_id)
            .order_by(Conversation.last_active_at.desc())
            .limit(1)
        )
        conv = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if conv and (now - conv.last_active_at) < CONVERSATION_TIMEOUT:
            # Still active — reuse it
            conv.last_active_at = now
            await session.commit()
            return conv.id
        else:
            # Expired or doesn't exist — create new
            conv = Conversation(chat_id=chat_id)
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            return conv.id
```

### Step 2: Load Previous Messages

```python
async def load_conversation_messages(conversation_id: int) -> list[dict]:
    """Load all messages for a conversation, formatted for Ollama."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at)
        )
        rows = result.scalars().all()

    messages = []
    for row in rows:
        msg = {"role": row.role, "content": row.content}
        if row.tool_calls_json:
            msg["tool_calls"] = json.loads(row.tool_calls_json)
        if row.tool_call_id:
            msg["tool_call_id"] = row.tool_call_id
        messages.append(msg)

    return messages
```

### Step 3: Save Each Turn As It Happens

Instead of saving once at the end (like `_save_conversation` does now), save each message as the agent loop runs:

```python
async def save_message(
    conversation_id: int,
    role: str,
    content: str,
    tool_calls: list | None = None,
    tool_call_id: str | None = None,
) -> None:
    async with SessionLocal() as session:
        msg = ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls_json=json.dumps(tool_calls) if tool_calls else None,
            tool_call_id=tool_call_id,
        )
        session.add(msg)
        await session.commit()
```

### Step 4: Modify `run_ai_agent`

Here's the key change in [run_ai_agent](file:///home/harsh/pocketing/pocketing/backend/mcp_pocketing/ai_client.py#L150-L293):

```python
async def run_ai_agent(user_message: str, chat_id: str = "") -> str:
    # ── NEW: Resolve conversation ──
    conversation_id = None
    if chat_id:
        conversation_id = await get_or_create_conversation(chat_id)

    # ... (MCP session setup stays the same) ...

    # ── NEW: Build messages with history ──
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

    if conversation_id:
        history = await load_conversation_messages(conversation_id)
        messages.extend(history)      # previous turns

    messages.append({"role": "user", "content": user_message})

    # ── NEW: Save the user message ──
    if conversation_id:
        await save_message(conversation_id, "user", user_message)

    # ... (agent loop stays the same, but save each turn) ...

    for iteration in range(10):
        response = await ask_qwen(messages, ollama_tools)
        assistant_message = response["message"]
        tool_calls = assistant_message.get("tool_calls", [])
        thought = assistant_message.get("content", "").strip()

        if not tool_calls:
            answer = thought or "✅ Done."
            # ── NEW: Save assistant's final answer ──
            if conversation_id:
                await save_message(conversation_id, "assistant", answer)
            break

        messages.append(assistant_message)
        # ── NEW: Save assistant's tool-calling turn ──
        if conversation_id:
            await save_message(
                conversation_id, "assistant", thought,
                tool_calls=tool_calls,
            )

        for tool_call in tool_calls:
            # ... (tool execution stays the same) ...
            result_content = json.dumps(tool_output)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id", ""),
                "content": result_content,
            })
            # ── NEW: Save tool result ──
            if conversation_id:
                await save_message(
                    conversation_id, "tool", result_content,
                    tool_call_id=tool_call.get("id", ""),
                )

    return answer
```

### What This Achieves

After this, your conversation flow works:

```
You: Find my resume /ai
    → Conversation #1 created
    → messages = [system, user("Find my resume")]
    → Qwen calls search_notes("resume"), finds it
    → All turns saved to DB

You: Send it to me /ai
    → Conversation #1 still active (< 30 min)
    → messages = [system, user("Find my resume"), assistant("Found..."), 
                  tool_result(...), assistant("Found harsh_mane_resume.pdf"),
                  user("Send it to me")]    ← Qwen now knows what "it" refers to
    → Qwen calls send_file with the resume
```

---

## Layer 3: Context Window Management

### The Problem

Qwen 3.5 4B has a context window (typically 32K tokens). If you dump 50 conversation turns plus tool results (which can be huge JSON blobs), you'll overflow and get garbage responses or errors.

### Strategy: Sliding Window + Tool Result Summarization

Don't overthink this for v1. Start simple:

```python
MAX_HISTORY_MESSAGES = 20  # Keep last 20 messages (roughly ~10 user/assistant pairs)
MAX_TOOL_RESULT_CHARS = 500  # Truncate old tool results

def trim_conversation_history(messages: list[dict]) -> list[dict]:
    """Keep recent messages, compress old tool results."""
    if len(messages) <= MAX_HISTORY_MESSAGES:
        return messages

    # Always keep the system prompt (first message)
    system = messages[:1]
    recent = messages[-MAX_HISTORY_MESSAGES:]

    # For any tool messages in the kept history that aren't in the
    # last 6 messages, truncate their content
    for i, msg in enumerate(recent):
        if msg["role"] == "tool" and i < len(recent) - 6:
            content = msg["content"]
            if len(content) > MAX_TOOL_RESULT_CHARS:
                msg["content"] = content[:MAX_TOOL_RESULT_CHARS] + "... [truncated]"

    return system + recent
```

Then in `run_ai_agent`, after building the messages list:

```python
messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
history = await load_conversation_messages(conversation_id)
messages.extend(history)
messages.append({"role": "user", "content": user_message})

# Trim before sending to Qwen
messages = trim_conversation_history(messages)
```

### Future Improvements (Not Now)

| Level | What | When |
|---|---|---|
| **v1 (now)** | Sliding window + truncate old tool results | This implementation |
| **v2** | Summarize old conversation context into a single "Previously:" message | When 20 messages isn't enough |
| **v3** | Vector DB for semantic retrieval of relevant past conversations | When you want cross-session memory ("remember last week when I...") |

---

## Do You Need a Vector DB?

**No. Not for this feature.** Here's the breakdown:

| Capability | What Solves It | Vector DB Needed? |
|---|---|---|
| "Send **it** to me" (same conversation) | In-session message history (this guide) | ❌ No |
| "What did I say about Redis **yesterday**?" | Query `conversation_messages` by `chat_id` + date range | ❌ No |
| "Find that conversation where I discussed **MCP architecture**" | Full-text search on `conversation_messages.content` | ❌ No (SQLite FTS5 works) |
| "Remember that I prefer dark mode" | User preferences table | ❌ No |
| "Based on everything I've ever told you, what should I focus on?" | Semantic search across all past conversations | ✅ Yes (eventually) |

You'd only need a vector DB (like ChromaDB, which runs locally) if you want **cross-session semantic memory** — the AI remembering things from weeks ago based on meaning, not keywords. That's a v3 feature.

---

## Files You Need to Touch

| File | Change |
|---|---|
| [models.py](file:///home/harsh/pocketing/pocketing/backend/app/models.py) | Add `Conversation` + `ConversationMessage` models |
| [database.py](file:///home/harsh/pocketing/pocketing/backend/app/database.py) | Import new models in `initialize_database()` |
| [ai_client.py](file:///home/harsh/pocketing/pocketing/backend/mcp_pocketing/ai_client.py) | Add conversation resolution, history loading, per-turn saving, context trimming |
| [telegram.py](file:///home/harsh/pocketing/pocketing/backend/app/telegram.py) | No changes needed — it already passes `chat_id` to `run_ai_agent()` |

### Optional But Recommended

Create a new file `backend/app/conversation_service.py` with:
- `get_or_create_conversation()`
- `load_conversation_messages()`
- `save_message()`
- `trim_conversation_history()`

This keeps [ai_client.py](file:///home/harsh/pocketing/pocketing/backend/mcp_pocketing/ai_client.py) clean and follows your existing pattern of `service.py` for business logic.

---

## Edge Cases to Think About

1. **Conversation expiry**: 30 minutes of inactivity → new conversation. This is configurable. Too short = loses context mid-conversation. Too long = Qwen gets confused by unrelated old messages.

2. **Explicit reset**: Consider a command like `/new` or `/reset` that forces a new conversation. Users will want this when Qwen gets stuck on old context.

3. **Tool call ordering**: When replaying history, the `tool_calls` in an assistant message must match the subsequent `tool` role messages by `tool_call_id`. If you store them in order, `ORDER BY created_at` handles this.

4. **The system prompt**: Always inject it fresh as `messages[0]`. Don't store it in the DB — if you update the prompt, you want the new one used with old conversations.

5. **Multi-turn tool calls**: Your current agent loop does up to 10 iterations per request. Each iteration might have multiple tool calls. All of those intermediate turns need to be saved too, not just the final answer.

---

## Recommended Implementation Order

1. **Add models** to `models.py`, update `database.py` imports
2. **Create `conversation_service.py`** with the 4 functions
3. **Modify `run_ai_agent()`** to use conversation service
4. **Test with Telegram**: "Find my resume /ai" → "Send it to me /ai"
5. **Add `trim_conversation_history()`** and tune the limits
6. **Add a `/new` reset command** in `telegram.py`
