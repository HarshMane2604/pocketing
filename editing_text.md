# Pocketing Telegram-Synced Text Editing

## Purpose

This document explains why editing a note in Pocketing previously did not update the corresponding Telegram message, how synchronized editing is now implemented, and how the 15-minute editing policy works.

## Original problem

Pocketing previously performed these steps when a browser-created note was saved:

1. Save the note in SQLite.
2. Call Telegram's `sendMessage` endpoint.
3. Ignore the `Message` object returned by Telegram.

When the note was edited later, `PATCH /api/notes/{id}` updated only SQLite. Telegram requires both the original `chat_id` and `message_id` to edit an existing message. Because Pocketing did not retain those identifiers and did not call `editMessageText`, it could not identify or update the Telegram message.

## Implemented behavior

### Web-created notes

A note created from Pocketing can be edited for 15 minutes after its original `created_at` time.

When Telegram successfully receives the new note, Pocketing stores the returned Telegram chat and message identifiers. A later content edit uses those identifiers to call Telegram's `editMessageText` endpoint.

If Telegram confirms the edit, Pocketing commits the same content to SQLite and broadcasts the updated note to connected browser sessions.

If Telegram rejects the edit or cannot be reached, Pocketing returns an error and keeps the original local content. This prevents the common failure mode where Pocketing shows one value and Telegram shows another.

### Telegram-origin notes

Notes captured from messages authored by the user in Telegram are read-only in Pocketing.

A normal bot cannot edit a message authored by the Telegram user. Allowing a local edit would recreate the synchronization problem, so Pocketing does not open the editor for these notes. The Telegram identifiers are still stored for traceability and possible future inbound-edit synchronization.

### Non-content changes

The 15-minute restriction applies only to text or structured rich-text changes. Users can still perform organizational actions after the window expires:

- Mark a note done or return it to the inbox.
- Pin or unpin a note.
- Reorder notes.
- Open threads, copy notes, and delete notes.

## Behavior matrix

| Note state | Text editing | Telegram behavior |
| --- | --- | --- |
| Web-created, Telegram reference present, less than 15 minutes old | Allowed | Original Telegram text message is edited |
| Web-created, Telegram reference missing, less than 15 minutes old | Allowed | Local-only edit; the UI tooltip reports that Telegram sync is unavailable |
| Web-created, 15 minutes old or older | Blocked | No Telegram request is made |
| Telegram-origin note | Blocked | Bot cannot edit the user's original Telegram message |
| Any note, pin/done/reorder-only update | Allowed | No Telegram text edit is required |

## Database changes

Two nullable columns were added to the `notes` table:

```text
telegram_chat_id     VARCHAR(100) NULL
telegram_message_id INTEGER      NULL
```

The fields are nullable for backward compatibility:

- Old notes created before this feature have no stored Telegram reference.
- Notes created while Telegram is unavailable may have no Telegram reference.
- Pocketing continues to load and display both cases normally.

`initialize_database()` checks the existing SQLite schema at startup and adds each missing column with `ALTER TABLE`. No destructive migration and no manual database reset are required.

## Note creation flow

For a browser-created note:

```text
Browser
  -> POST /api/notes
  -> validate and save note in SQLite
  -> Telegram sendMessage
  -> read result.chat.id and result.message_id
  -> store both identifiers on the note
  -> return and broadcast the synchronized note
```

The Telegram reference is stored only after Telegram confirms that the message was created.

If initial Telegram delivery fails, the note remains saved locally, matching Pocketing's previous offline-friendly behavior. Its `telegram_sync_available` response field is `false`.

## Note editing flow

For `PATCH /api/notes/{note_id}` containing `content` or `structured_content`:

1. Load the note.
2. Confirm that it was created from Pocketing rather than authored by the Telegram user.
3. Calculate `created_at + 15 minutes` and reject an expired edit.
4. Validate the structured rich-text document.
5. Render the rich document into the readable plain-text representation used by Telegram.
6. If a Telegram reference exists and the visible text changed, call `editMessageText` with:

   ```json
   {
     "chat_id": "stored chat ID",
     "message_id": 123,
     "text": "updated note text"
   }
   ```

7. Commit the local content only after Telegram confirms the edit.
8. Broadcast `note.updated` over the existing WebSocket connection.

Formatting-only changes whose plain-text representation is unchanged are stored in Pocketing without sending a redundant Telegram edit request.

## API response fields

Every serialized note now includes:

```json
{
  "can_edit": true,
  "editable_until": "2026-08-21T12:15:00Z",
  "telegram_sync_available": true
}
```

- `can_edit`: Server-calculated policy result at response time.
- `editable_until`: Authoritative UTC deadline based on the original note creation time.
- `telegram_sync_available`: Indicates whether Pocketing has the Telegram identifiers required to synchronize text edits.

Telegram chat and message identifiers are intentionally not returned to the frontend.

## HTTP errors

Content edit requests may return:

- `403`: The 15-minute edit window expired.
- `409`: The note originated from a user-authored Telegram message and cannot be edited by the bot.
- `422`: The content or structured rich-text document is invalid.
- `502`: Telegram could not update a mirrored message. Pocketing keeps the original local note.

## Frontend behavior

The frontend uses the server-provided deadline and also runs a local timer so the UI becomes read-only when the deadline passes without requiring a page refresh.

While editing is available:

- The note shows an `edit Xm` indicator.
- Hover text reports the remaining time.
- The tooltip states whether Telegram synchronization is available.
- Clicking the note opens the rich-text editor.

When time expires:

- The editor is closed if it is currently open.
- Unsaved editor changes are discarded.
- The note no longer has the editable cursor or click behavior.
- The backend still enforces the deadline, so changing the browser clock or manually calling the API cannot bypass the restriction.

## Rich-text and Telegram

Pocketing continues to store the complete validated Tiptap JSON document in `structured_content`.

Telegram currently receives Pocketing's readable plain-text rendering. This preserves list markers, checklist markers, blockquotes, dividers, code text, line breaks, and emojis without exposing editor JSON or raw HTML.

Pure formatting differences such as changing plain `hello` to bold `hello` remain visible in Pocketing, but Telegram's plain-text message still reads `hello`. Extending Telegram entity/formatting synchronization can be implemented separately.

Pocketing's 4,000-character limit remains inside Telegram's 4,096-character text-message limit.

## Attachments

Pocketing sends note text and uploaded files as separate Telegram messages. Editing a note updates the mirrored text message. It does not replace uploaded files or edit the separate file captions.

## Legacy notes

Old notes remain readable and retain their existing rich/plain-text compatibility.

Most legacy notes will already be older than 15 minutes and therefore read-only. A recent legacy web note without a stored Telegram reference can be edited locally during its remaining window, but Telegram cannot be updated because the historical message ID cannot be recovered reliably.

## Files changed

- `backend/app/models.py`: Telegram reference columns.
- `backend/app/database.py`: additive SQLite startup migration.
- `backend/app/telegram.py`: message-reference capture and `editMessageText` support.
- `backend/app/api.py`: reference persistence, edit policy, synchronization, and failure handling.
- `backend/app/service.py`: edit-window helpers and response metadata.
- `backend/app/schemas.py`: editing metadata in note responses.
- `backend/tests/test_editing.py`: policy and synchronization tests.
- `frontend/src/types.ts`: new note metadata types.
- `frontend/src/components/NoteRow.tsx`: timer-based editing UI and read-only behavior.

## Automated tests

Run backend tests from the repository root:

```powershell
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

The test suite covers:

- A recent web note being editable.
- Expiration at exactly 15 minutes.
- Telegram-origin notes being read-only.
- UTC handling for SQLite timestamps.
- Capturing Telegram's returned message reference.
- Calling `editMessageText` with the correct chat and message IDs.
- Rejecting expired API edits.
- Keeping local content unchanged when Telegram fails.
- Committing both Telegram and local changes after a successful edit.

Build the frontend with:

```powershell
cd frontend
npm run build
```

## Manual verification

1. Restart Pocketing so the additive database migration runs.
2. Create a text note from the Pocketing browser interface.
3. Confirm that it appears in Telegram.
4. Within 15 minutes, click the Pocketing note and change its text.
5. Save the edit.
6. Confirm that Telegram updates the original message instead of receiving a second message.
7. Temporarily disconnect Telegram and attempt another edit to a synchronized note.
8. Confirm that Pocketing shows an error and retains the previous local content.
9. After 15 minutes, confirm that clicking the note no longer opens the editor.
10. Confirm that pin, done, reorder, copy, delete, and thread controls still work.
11. Confirm that a Telegram-origin note is read-only in Pocketing.

## Known limitations

- Telegram-origin user messages cannot be edited by the Pocketing bot.
- Historical Telegram message identifiers cannot be reconstructed for old notes.
- Thread messages do not currently have an editing UI, so synchronized editing applies to primary notes.
- Telegram receives the plain-text projection rather than every Pocketing rich-text style.
- Editing note text does not modify separately sent attachment messages or their captions.

## Telegram reference

Pocketing uses Telegram's official Bot API behavior:

- `sendMessage` returns the sent `Message`, including its `message_id`.
- `editMessageText` targets an existing text message using `chat_id` and `message_id`.

Official reference: <https://core.telegram.org/bots/api#editmessagetext>
