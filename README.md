# Pocketing

A personal note-taking and file-management dashboard connected to Telegram. Send notes, files, and commands from your phone via Telegram and see them instantly in your browser. Trigger the AI assistant with `/ai` to search, create, or reason about your data using a local Qwen model.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS (PWA) |
| Backend | Python, FastAPI, SQLite, WebSockets |
| AI Agent | Qwen (via Ollama) + MCP (Model Context Protocol) |
| Messaging | Telegram Bot API long-polling |

---

## Architecture

```
Browser (PWA)
    │  REST + WebSocket
    ▼
FastAPI  (app/main.py  —  port 8010)
    ├── app/api.py          REST & WebSocket routes
    ├── app/service.py      business logic
    ├── app/models.py       SQLite models (SQLAlchemy)
    ├── app/telegram.py     Telegram long-poll bridge
    └── mcp_pocketing/      AI agent layer
          ├── ai_client.py  Qwen agent loop (Ollama)
          ├── tool_router.py smart tool filtering
          └── server.py     MCP tool server (stdio subprocess)
```

Telegram messages arrive via long-polling in `telegram.py`. Messages ending with `/ai` are routed through the Qwen agent (`ai_client.py`), which spawns `server.py` as a subprocess and calls MCP tools in a loop to fulfil the request. All other messages become notes.

---

## Run Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com/) running locally with the Qwen model pulled:

  ```bash
  ollama pull vaultbox/qwen3.5-4b
  ```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\Activate.ps1       # Windows PowerShell

pip install -r requirements.txt
cp .env.example .env               # then fill in your values
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

The SQLite database is created automatically at `backend/data/pocketing.db`.

### Frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). In production the PWA is compiled into `frontend/dist/` and served directly by FastAPI on port 8010.

---

## Install as a Background Service (Linux)

This production setup runs everything in one FastAPI process — UI, API, WebSocket, SQLite, Telegram bridge, and AI agent — available only on your own machine at [http://127.0.0.1:8010](http://127.0.0.1:8010).

```bash
bash scripts/linux/install-startup.sh
```

This registers a `systemd --user` service, a desktop shortcut, and a login autostart entry. Useful commands:

```bash
# Restart the backend
systemctl --user restart pocketing

# Reload systemd after editing the service file
systemctl --user daemon-reload

# Enable / start / inspect the MCP service
systemctl --user enable pocketing-mcp.service
systemctl --user start pocketing-mcp.service
systemctl --user status pocketing-mcp.service --no-pager
```

Remove only the startup entries (keeps your notes):

```bash
bash scripts/linux/uninstall-startup.sh
```

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-startup.ps1
```

Builds the PWA, registers `Pocketing Service` in Task Scheduler, and adds a desktop shortcut. Uninstall:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\uninstall-startup.ps1
```

---

## Connect Telegram

1. Message `@BotFather` in Telegram, run `/newbot`, and copy the token.
2. Add it to `backend/.env`:

   ```dotenv
   TELEGRAM_BOT_TOKEN=123456789:your_token_here
   ```

3. Restrict the bot to your own chat (recommended). Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`, find your numeric `chat.id`, and add it:

   ```dotenv
   TELEGRAM_ALLOWED_CHAT_ID=123456789
   ```

4. Restart the backend and send the bot one message to pair your chat.

> **Never commit `backend/.env` or share the bot token.**

---

## AI Assistant (`/ai`)

Append `/ai` to any Telegram message to invoke the Qwen AI agent:

```
find my Redis note /ai
search github for my Webscrapper-Framework PRs /ai
write a Python hello-world script and run it /ai
```

The agent uses [MCP tools](backend/mcp_pocketing/README.md) to search notes, read files, run sandbox commands, browse the web, and interact with GitHub. See [`backend/mcp_pocketing/README.md`](backend/mcp_pocketing/README.md) for full documentation of the AI layer.

Configure the model in `backend/.env`:

```dotenv
OLLAMA_URL=http://127.0.0.1:11434/api/chat
OLLAMA_MODEL=vaultbox/qwen3.5-4b
```

---

## REST API

All endpoints are under the `/api` prefix. A live Swagger UI is available at [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs).

### Notes

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/notes` | List notes; accepts optional `?search=` |
| `POST` | `/api/notes` | Create a note |
| `PATCH` | `/api/notes/{id}` | Update content, pinned, or done state |
| `DELETE` | `/api/notes/{id}` | Delete a note |
| `PUT` | `/api/notes/reorder` | Reorder notes |
| `GET` | `/api/notes/{id}/thread` | Get thread messages for a note |
| `POST` | `/api/notes/{id}/thread` | Add a thread message |
| `DELETE` | `/api/notes/{id}/thread/{msg_id}` | Delete a thread message |

### Files

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/files` | List uploaded files |
| `GET` | `/api/files/{id}/info` | Get file metadata |
| `GET` | `/api/files/{storage_key}` | Download a file |
| `GET` | `/api/files/{id}/content` | Read text content from a file |
| `DELETE` | `/api/files/{id}` | Delete a file |
| `POST` | `/api/files/{id}/send` | Send a file to Telegram |
| `POST` | `/api/files/send-local` | Send a local sandbox file to Telegram |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/api/status` | Safe runtime diagnostics (Telegram status, no token) |
| `WS` | `/ws` | Real-time note events |

---

## Environment Variables

All settings live in `backend/.env` (see `backend/.env.example`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/pocketing.db` | SQLite path |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS allowed origin |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_ALLOWED_CHAT_ID` | — | Restrict bot to one chat |
| `MAX_UPLOAD_SIZE` | `52428800` (50 MB) | Max file upload size |
| `UPLOAD_DIR` | `data/uploads` | File upload directory |
| `OLLAMA_URL` | `http://127.0.0.1:11434/api/chat` | Ollama API endpoint |
| `OLLAMA_MODEL` | `vaultbox/qwen3.5-4b` | AI model to use |
| `GITHUB_PAT` | — | GitHub PAT for AI GitHub tools |

---

## Project Structure

```
pocketing/
├── backend/
│   ├── app/                    FastAPI application
│   │   ├── main.py             App entrypoint, middleware, lifespan
│   │   ├── api.py              REST & WebSocket routes
│   │   ├── models.py           SQLAlchemy ORM models
│   │   ├── schemas.py          Pydantic request/response schemas
│   │   ├── service.py          Business logic
│   │   ├── telegram.py         Telegram long-poll bridge + /ai dispatch
│   │   ├── conversation_service.py  Conversation history persistence
│   │   ├── config.py           Pydantic settings
│   │   ├── database.py         Async SQLite engine
│   │   └── rich_text.py        Rich text → plain text conversion
│   ├── mcp_pocketing/          AI agent + MCP server
│   │   ├── server.py           MCP tool definitions (22 tools)
│   │   ├── ai_client.py        Qwen agent loop
│   │   ├── tool_router.py      Keyword + LLM tool filtering
│   │   ├── client.py           Debug MCP client
│   │   └── system_prompt.md    Base AI instructions
│   ├── pocketing_logging/      Structured logging (backend, telegram, AI)
│   ├── character.md            AI personality profile (Mira)
│   ├── data/                   SQLite DB + uploaded files
│   ├── sandbox/                AI agent local workspace
│   └── requirements.txt
├── frontend/                   React + Vite PWA
├── scripts/
│   ├── linux/                  systemd service install/uninstall
│   └── windows/                Task Scheduler install/uninstall
└── Documentation/
    └── codebase.md
```
