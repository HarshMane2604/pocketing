# Memory Inbox

A tiny two-way dashboard for short notes sent between your laptop and Telegram.
It has no AI, projects, tags, reminders, or productivity system—just one inbox.

## Stack

- React, TypeScript, Vite, and Tailwind CSS
- Python and FastAPI
- SQLite
- WebSockets for live browser updates
- Telegram Bot API long polling for phone capture

## Run locally

### Recommended: install as a desktop app

This production setup uses one background FastAPI process for the UI, API,
WebSocket, SQLite, and Telegram bridge. The app is available only on your own
computer at [http://127.0.0.1:8010](http://127.0.0.1:8010).

#### Windows

Open PowerShell and run:

```powershell
cd C:\Users\harshmane\harsh1\notes_app
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-startup.ps1
```

This builds the PWA, registers `Memory Inbox Service` in Task Scheduler, adds a
desktop shortcut, and opens the compact app window automatically at login.
Uninstall the startup entries without deleting notes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\uninstall-startup.ps1
```

#### Linux

Run:

```bash
cd /path/to/notes_app
bash scripts/linux/install-startup.sh
```

This installs a `systemd --user` service plus desktop and login-autostart
entries. Remove only those startup entries with:

```bash
bash scripts/linux/uninstall-startup.sh
```

You can also install the PWA from Edge or Chrome's address-bar install button.
On Windows, Edge can enable **Auto-start on device login** from `edge://apps`.

### Development mode

#### Backend

```powershell
cd C:\Users\harshmane\harsh1\notes_app\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

The SQLite database is created automatically at `backend/data/memory_inbox.db`.

#### Frontend

Open a second terminal:

```powershell
cd C:\Users\harshmane\harsh1\notes_app\frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Development mode uses two
processes; the installed desktop setup above uses only FastAPI.

## Keeping it online

The local service and Telegram bridge run while the computer is awake and you
are logged in. Sleep, hibernation, shutdown, or loss of internet pauses message
delivery until the computer resumes. For true 24/7 delivery, move the backend
to an always-online server later.

## Connect Telegram

1. In Telegram, message `@BotFather`, run `/newbot`, and copy the token.
2. Put it in `backend/.env`:

   ```dotenv
   TELEGRAM_BOT_TOKEN=123456789:your_token_here
   ```

3. Recommended: send the bot one message, then visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`. Copy the numeric
   `message.chat.id` into:

   ```dotenv
   TELEGRAM_ALLOWED_CHAT_ID=123456789
   ```

4. Restart the backend, then send the bot one normal message to pair your chat.
   Text messages and media captions appear in the browser instantly. Notes added
   in the browser are saved and sent back to Telegram. Bot commands such as
   `/start` are ignored.

Never commit `backend/.env` or share the bot token.

## API

- `GET /api/notes` — list notes; accepts optional `?search=`
- `POST /api/notes` — create a note
- `PATCH /api/notes/{id}` — update content, pinned, or done state
- `DELETE /api/notes/{id}` — delete a note
- `GET /api/status` — safe Telegram/runtime diagnostics (never returns the token)
- `WS /ws` — real-time note events

## WhatsApp later

Add a verified WhatsApp Cloud API webhook beside `backend/app/telegram.py` and
call `create_note(session, content)` from `backend/app/service.py`. The shared
service already saves the note and broadcasts it to the frontend, so WhatsApp
does not require frontend changes.
"# pocketing" 
"# pocketing" 
