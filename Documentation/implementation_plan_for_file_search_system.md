# File Search & Management System

You have file upload working (notes & threads can have attachments, drag-and-drop, preview, lightbox, download, delete). What's missing is a dedicated view to **browse, search, filter, and manage all files** across the app — right now files are only visible inline on the notes they belong to.

## Proposed Changes

### Backend — New `/api/files` list endpoint

#### [MODIFY] [api.py](file:///home/harsh/pocketing/pocketing/backend/app/api.py)

Add a `GET /api/files` endpoint that returns all attachments with optional filters:

- **`search`** — substring match on `filename` (case-insensitive)
- **`type`** — filter by media category: `image`, `video`, `audio`, `document` (maps to content_type prefixes)
- **`sort`** — `newest` (default), `oldest`, `largest`, `smallest`, `name`
- **`limit`** / `offset`** — pagination (default 50 per page)

Each result includes the parent note/thread-message content snippet so the user knows where the file lives.

#### [MODIFY] [schemas.py](file:///home/harsh/pocketing/pocketing/backend/app/schemas.py)

Add `FileSearchResult` response schema with fields: attachment info + `parent_type` (`"note"` | `"thread"`) + `parent_id` + `parent_content` (truncated to 80 chars).

---

### Frontend — New "Files" view

#### [NEW] [FilesView.tsx](file:///home/harsh/pocketing/pocketing/frontend/src/components/FilesView.tsx)

A full-page panel (same pattern as `ThreadView`) with:

- **Search bar** at the top with real-time filtering by filename
- **Type filter chips** — All / Images / Videos / Audio / Documents
- **Sort dropdown** — Newest, Oldest, Largest, Smallest, Name
- **File grid/list** showing thumbnails for images/video, icons for other types
- Each file card shows: thumbnail/icon, filename, size, date, parent note snippet
- Actions per file: **download**, **delete**, **open parent note**
- **Empty state** when no files match

#### [MODIFY] [api.ts](file:///home/harsh/pocketing/pocketing/frontend/src/api.ts)

Add `filesApi.list(params)` method to call the new endpoint.

#### [MODIFY] [types.ts](file:///home/harsh/pocketing/pocketing/frontend/src/types.ts)

Add `FileSearchResult` type.

#### [MODIFY] [Icons.tsx](file:///home/harsh/pocketing/pocketing/frontend/src/components/Icons.tsx)

Add `FolderIcon` / `FilterIcon` / `SortIcon` if not already present.

#### [MODIFY] [App.tsx](file:///home/harsh/pocketing/pocketing/frontend/src/App.tsx)

Add a "Files" button in the header that switches to the `FilesView`. When a user clicks "open parent note" on a file, navigate back to the main view with that note highlighted, or open its thread.

#### [MODIFY] [index.css](file:///home/harsh/pocketing/pocketing/frontend/src/index.css)

Add styles for the files view: grid layout, filter chips, sort controls, file cards with hover states. Follows the existing design language (monochrome, warm, Inter font, `--bg-*` / `--text-*` tokens, same radius and transitions).

## Verification Plan

### Manual Verification
1. Upload various file types (images, PDFs, audio, video) across notes and thread messages
2. Open the Files view and verify all files appear
3. Test search by filename
4. Test type filters (Images, Videos, etc.)
5. Test sort options
6. Test delete from the files view
7. Test "go to note" navigation
8. Verify dark mode styling
9. Verify mobile responsiveness
