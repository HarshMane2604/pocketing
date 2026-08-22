# Pocketing Backend — Full Change Log

## Change 1: Telegram → Qwen AI Integration (via MCP)

### Architecture

    Telegram: "find my Redis note /ai"
         │
         ▼
    app/telegram.py         detects " /ai" suffix
         │
         ▼
    mcp_pocketing/
      ai_client.py          Qwen agent loop → calls MCP tools
         │  spawns subprocess
         ▼
      server.py             MCP tools → Pocketing REST API (:8010)
         │
         ▼
    Qwen response → ai_conversations table → Telegram reply

### Files

    mcp_pocketing/__init__.py       package marker
    mcp_pocketing/server.py         MCP tools (fixed: removed bad import, json→data)
    mcp_pocketing/ai_client.py      run_ai_agent() + standalone main()
    app/telegram.py                 suffix /ai trigger, chat_id passed to agent
    app/models.py                   AiConversation model (separate table)
    app/database.py                 imports AiConversation for auto-create
    app/config.py                   ollama_url, ollama_model settings

### Usage

    find my Redis note /ai
    create a note: buy groceries /ai
    what's in my resume PDF? /ai

---

## Change 2: Bug Fix — create_note MCP tool

### Problem

    server.py used json={"content": ...} to POST /api/notes
    but the endpoint expects Form(...) data → 422 every time

### Fix

    json= changed to data= in server.py line 206

---

## Change 3: Logging System

### Directory Structure

    backend/pocketing_logging/
      __init__.py
      logger.py                 central setup module
      logs/
        2026-08-22/
          ai/
            qwen.log            full Qwen agent trace
          backend/
            api.log             all API request/response logs
        2026-08-23/
          ...

### AI Logs (qwen.log) — what gets logged

    ═══════════════════════════════════════════════════════════════
    [2026-08-22 21:53:00] NEW AI REQUEST
      Chat ID:  123456789
      User:     "create a note: Need to work hard"
    ───────────────────────────────────────────────────────────────
    [2026-08-22 21:53:01] MCP SESSION STARTED
      Server:   mcp_pocketing/server.py
      Tools:    list_notes, search_resources, create_note, ...
    [2026-08-22 21:53:02] QWEN ITERATION 1
      Thought:  (Qwen's reasoning)
      Tool Call: create_note
      Arguments: {"content": "Need to work hard"}
    [2026-08-22 21:53:03] MCP RESULT (120ms):
      Tool:   create_note
      Output: {"id": 42, "content": "Need to work hard", ...}
    [2026-08-22 21:53:04] QWEN ITERATION 2
      Final Answer: "Created the note for you!"
    [2026-08-22 21:53:04] AI REQUEST COMPLETE
      Status:   SUCCESS
      Duration: 4.2s
      Saved to DB: yes (ai_conversations.id = 15)
    ═══════════════════════════════════════════════════════════════

### Backend Logs (api.log) — what gets logged

    [2026-08-22 22:27:24] INFO     POST /api/notes → 201 (1332ms)
      Request:  (multipart form data)
    [2026-08-22 22:27:30] INFO     GET /api/notes?search=redis → 200 (5ms)
    [2026-08-22 22:27:35] INFO     PATCH /api/notes/42 → 200 (12ms)
      Request:  {"is_done": true}

Skipped (too noisy): /ws, /health, /api/status, /assets/, /icons/

### Files

    pocketing_logging/__init__.py   package marker
    pocketing_logging/logger.py     DailyFileHandler, setup_logging(), get_ai/backend_logger()
    app/main.py                     setup_logging() at startup + APILoggingMiddleware
    mcp_pocketing/ai_client.py      detailed structured AI logging in run_ai_agent()

---

## Database

    notes              unchanged
    thread_messages    unchanged
    attachments        unchanged
    app_settings       unchanged
    ai_conversations   NEW: id, chat_id, user_query, ai_response, created_at

---

## Restart

    systemctl --user restart pocketing

## View Logs

    # Today's AI logs
    cat ~/pocketing/pocketing/backend/pocketing_logging/logs/$(date +%Y-%m-%d)/ai/qwen.log

    # Today's backend logs
    cat ~/pocketing/pocketing/backend/pocketing_logging/logs/$(date +%Y-%m-%d)/backend/api.log

    # AI conversation history in DB
    sqlite3 ~/pocketing/pocketing/backend/data/pocketing.db \
      "SELECT id, user_query, ai_response, created_at FROM ai_conversations ORDER BY created_at DESC LIMIT 10;"
