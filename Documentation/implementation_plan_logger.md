# Bug Fix + Logging System

## Part 1 — Bug Fix (create_note failing)

> [!CAUTION]
> **Root Cause:** `mcp_pocketing/server.py` sends `json={"content": ...}` to `POST /api/notes`, but the backend expects `Form(...)` data — guaranteed 422 error every time.

#### [MODIFY] [server.py](file:///home/harsh/pocketing/pocketing/backend/mcp_pocketing/server.py)
```diff
- response = await client.post(
-     f"{POCKETING_API}/api/notes",
-     json={"content": content.strip()},
-     timeout=10.0,
- )
+ response = await client.post(
+     f"{POCKETING_API}/api/notes",
+     data={"content": content.strip()},   # Form data, not JSON
+     timeout=10.0,
+ )
```

---

## Part 2 — Logging System

### Directory Structure

```
backend/
  logging/
    logger.py          ← central logging setup
    2026-08-22/        ← daily folder (auto-created)
      ai/
        qwen.log       ← full AI trace for the day
      backend/
        api.log        ← all API request/response logs
    2026-08-23/
      ai/
        qwen.log
      backend/
        api.log
    ...
```

### What Gets Logged

#### AI Logs (`logging/<date>/ai/qwen.log`)

Every `/ai` request produces a full trace block:

```
═══════════════════════════════════════════════════════════════
[2026-08-22 21:53:00] NEW AI REQUEST
  Chat ID:  123456789
  User:     "create a note: Need to work hard"
───────────────────────────────────────────────────────────────
[2026-08-22 21:53:01] MCP SESSION STARTED
  Server:   mcp_pocketing/server.py
  Tools:    list_notes, search_resources, create_note, ...
[2026-08-22 21:53:02] QWEN ITERATION 1
  Thought:  (assistant message content, if any)
  Tool Call: create_note
  Arguments: {"content": "Need to work hard"}
[2026-08-22 21:53:03] MCP RESULT
  Tool:     create_note
  Output:   {"id": 42, "content": "Need to work hard", ...}
[2026-08-22 21:53:04] QWEN ITERATION 2
  Final Answer: "I've created the note 'Need to work hard' for you!"
[2026-08-22 21:53:04] AI REQUEST COMPLETE
  Status:   SUCCESS
  Duration: 4.2s
  Saved to DB: yes (ai_conversations.id = 15)
═══════════════════════════════════════════════════════════════
```

#### Backend Logs (`logging/<date>/backend/api.log`)

Every API call:
```
[2026-08-22 21:53:03] POST /api/notes → 201 (12ms)
  Request:  content="Need to work hard"
  Response: {"id": 42, "content": "Need to work hard", ...}

[2026-08-22 21:53:10] GET /api/notes → 200 (5ms)
  Params:   search=redis
  Response: [2 notes]
```

---

### Proposed Changes

#### [NEW] [logger.py](file:///home/harsh/pocketing/pocketing/backend/logging/logger.py)

Central module:
- `setup_logging()` — called once at backend startup
- Creates daily date folders (`2026-08-22/ai/`, `2026-08-22/backend/`)
- Returns configured loggers for AI and backend
- Uses `TimedRotatingFileHandler` — new day = new folder automatically

#### [MODIFY] [ai_client.py](file:///home/harsh/pocketing/pocketing/backend/mcp_pocketing/ai_client.py)

Replace all `logger.info/debug` calls with detailed structured logging:
- Log every iteration, every tool call, every MCP result
- Log timing, final answer, errors with full tracebacks
- Uses the AI file logger from `logging/logger.py`

#### [MODIFY] [main.py](file:///home/harsh/pocketing/pocketing/backend/app/main.py)

Call `setup_logging()` at app startup.

#### [NEW] Backend API logging middleware

FastAPI middleware that logs every request/response to the backend log file automatically — no changes needed to individual route handlers.

---

## Verification Plan

1. Fix the create_note bug → send `"create a note: test /ai"` in Telegram → note should be created
2. Check `backend/logging/2026-08-22/ai/qwen.log` for full agent trace
3. Check `backend/logging/2026-08-22/backend/api.log` for API call logs
