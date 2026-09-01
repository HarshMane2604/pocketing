# mcp_pocketing

The **MCP (Model Context Protocol) layer** for the Pocketing backend. This package exposes a local MCP server that gives the Qwen AI agent structured, tool-based access to Pocketing's data and external services. The AI agent talks to this server over stdio and calls its tools in an agentic loop.

---

## Architecture

```
Telegram message  ──►  TelegramBridge (app/telegram.py)
                              │
                              ▼
                    run_ai_agent()  (ai_client.py)
                              │
             ┌────────────────┴───────────────────┐
             │   Tool Router  (tool_router.py)     │
             │  keyword / LLM-based classification │
             └────────────────┬───────────────────┘
                              │  filtered tool list
                              ▼
                    MCP Server (server.py)  [stdio subprocess]
                    ┌──────────────────────────────┐
                    │  Notes │ Files │ Sandbox      │
                    │  Web   │ GitHub│ ...          │
                    └──────────────────────────────┘
                              │
                        Pocketing REST API  (http://127.0.0.1:8010)
```

---

## Files

| File | Purpose |
|---|---|
| `server.py` | MCP server — defines all tools exposed to the AI agent |
| `ai_client.py` | AI agent loop — connects to the server, calls Qwen via Ollama, handles multi-turn tool use |
| `tool_router.py` | Smart tool filtering — narrows the tool list per-request using keyword matching then LLM classification |
| `client.py` | Minimal debug client for manually testing the MCP server from the terminal |
| `system_prompt.md` | Core instructions given to the AI at the start of every session |
| `__init__.py` | Package marker |

The **AI character / personality** is loaded from `../character.md` (one level up, in the `backend/` root) and prepended to `system_prompt.md` at runtime.

---

## MCP Tools

The server exposes tools grouped into five categories:

### 📝 Notes
| Tool | Description |
|---|---|
| `list_notes` | List all notes, with optional `is_done` / `is_pinned` filters |
| `search_resources` | Full-text search across saved notes |
| `get_resource` | Fetch a single note by ID |
| `create_note` | Save a new note |
| `update_note` | Edit an existing note |

### 📁 Files
| Tool | Description |
|---|---|
| `search_files` | Search uploaded file attachments |
| `get_file_info` | Get metadata for a specific file |
| `read_file_info` | Read text content from a file |
| `send_file` | Send a file to the user via Telegram |

### 🖥️ Sandbox
| Tool | Description |
|---|---|
| `write_file` | Write a file into the local sandbox workspace |
| `run_local_command` | Execute a shell command in the sandbox |
| `create_local_directory` | Create a directory in the sandbox |
| `list_local_files` | List files in the sandbox |
| `read_local_file` | Read a file from the sandbox |
| `patch_local_file` | Apply a patch to a sandbox file |
| `grep_local_files` | Search file contents in the sandbox |
| `zip_sandbox_workspace` | Zip the entire sandbox directory |

### 🌐 Web
| Tool | Description |
|---|---|
| `search_web` | DuckDuckGo HTML search |
| `fetch_url` | Fetch and parse a URL as clean text |

### 🐙 GitHub
| Tool | Description |
|---|---|
| `search_github` | Search GitHub repositories |
| `list_github_prs` | List pull requests for a given repo |
| `create_github_pr` | Create a pull request |

---

## Tool Router

`tool_router.py` prevents the agent from being overwhelmed by the full tool list on every request. It classifies each incoming message into one or more categories and sends only the relevant tools to Qwen:

1. **Keyword matching** — fast, zero-cost: checks for phrases like `"note"`, `"file"`, `"github"`, `"search the web"`, etc.
2. **LLM classification** — fallback when keywords give no match: asks Qwen itself to reply with a single word (`notes`, `files`, `sandbox`, `web`, `github`, or `chat`).
3. **Full toolset fallback** — used if the LLM classification call fails outright.

If the message is classified as `chat` (pure conversation, no tools needed), an empty tool list is returned and Qwen responds directly.

---

## AI Agent Loop (`ai_client.py`)

`run_ai_agent(user_message, chat_id)` is the main entry point called by the Telegram bridge:

1. Spawns `server.py` as a stdio subprocess via the MCP SDK.
2. Retrieves the filtered tool list from the tool router.
3. Loads conversation history from the database (keyed by `chat_id`).
4. Sends the message to Qwen (via Ollama) with the tool list.
5. If Qwen calls a tool, executes it against the MCP server and appends the result.
6. Repeats up to **20 iterations** until Qwen gives a final text answer.
7. Saves the final answer and all messages to the `ai_conversations` table.
8. Returns the answer string to the Telegram bridge.

All iterations are logged in detail to the structured AI log file (`pocketing_logging`).

---

## Configuration

Settings are loaded from `.env` / `.env.development` in the `backend/` directory (via `app/config.py`):

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434/api/chat` | Ollama API endpoint |
| `OLLAMA_MODEL` | `vaultbox/qwen3.5-4b` | Model to use |
| `GITHUB_PAT` | — | GitHub personal access token (primary) |
| `GITHUB_PAT_OEMMART` | — | GitHub PAT for secondary org |

---

## Running Standalone (Debug)

To test the agent directly from the terminal without Telegram:

```bash
cd backend
python -m mcp_pocketing.ai_client
```

Edit the `user_request` variable at the bottom of `ai_client.py` to change the test query.

To test the raw MCP server without the agent:

```bash
cd backend/mcp_pocketing
python client.py
```

---

## Dependencies

Key packages (see `backend/requirements.txt`):

- `mcp` — MCP SDK (server + stdio client transport)
- `httpx` — async HTTP for Ollama and Pocketing REST API calls
- `fastapi` / `uvicorn` — the outer Pocketing API that this package calls
- `sqlalchemy[asyncio]` + `aiosqlite` — async SQLite for conversation persistence
- `pydantic-settings` — settings management
