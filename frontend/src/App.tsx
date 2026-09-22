import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';

import { notesApi, websocketUrl } from '@/api';
import { CheckIcon, SearchIcon, SendIcon, XIcon } from '@/components/Icons';
import { SortableNoteRow } from '@/components/SortableNoteRow';
import { NoteRow } from '@/components/NoteRow';
import { ThreadView } from '@/components/ThreadView';
import { ThemeToggle } from '@/components/ThemeToggle';
import { FilesView } from '@/components/FilesView';
import { LinksView } from '@/components/LinksView';
import { OnHoldView } from '@/components/OnHoldView';
import { NavRail, type View } from '@/components/NavRail';
import { FileUploadButton } from '@/components/FileUploadButton';
import { RichTextEditor, type RichTextChange } from '@/components/RichTextEditor';
import type { JSONContent } from '@tiptap/core';
import type { Note, NoteEvent, NoteUpdate, TelegramStatus } from '@/types';

type ConnectionState = 'connecting' | 'connected' | 'offline';

function newestFirst(notes: Note[]): Note[] {
  return [...notes].sort((a, b) => {
    const pA = a.priority || 0;
    const pB = b.priority || 0;
    if (pA === 0 && pB !== 0) return 1;
    if (pA !== 0 && pB === 0) return -1;
    if (pA !== 0 && pB !== 0 && pA !== pB) return pA - pB;

    const timeDiff = new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    if (timeDiff !== 0) return timeDiff;
    return b.id - a.id;
  });
}

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  if (!count) return null;
  return (
    <section className="section">
      <div className="section-header">
        <span className="section-label">{title}</span>
        <span className="section-count">{count}</span>
      </div>
      {children}
    </section>
  );
}

export default function App() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [links, setLinks] = useState<Note[]>([]);
  const [onHoldNotes, setOnHoldNotes] = useState<Note[]>([]);
  const [draft, setDraft] = useState('');
  const [draftDocument, setDraftDocument] = useState<JSONContent | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyIds, setBusyIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState('');
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null);
  const [view, setView] = useState<View>('notes');
  const [activeThread, setActiveThread] = useState<Note | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [linkToast, setLinkToast] = useState(false);
  const linkToastTimer = useRef<number | undefined>(undefined);
  const reconnectTimer = useRef<number | undefined>(undefined);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  function handleDragEnd(event: DragEndEvent, list: Note[]) {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = list.findIndex(n => n.id === active.id);
      const newIndex = list.findIndex(n => n.id === over.id);
      const newOrder = arrayMove(list, oldIndex, newIndex);
      
      setNotes(current => current.map(note => {
        const index = newOrder.findIndex(n => n.id === note.id);
        if (index !== -1) {
          return { ...note, priority: index + 1 };
        }
        return note;
      }));
      
      notesApi.reorder(newOrder.map(n => n.id)).catch((err: Error) => setError(err.message));
    }
  }

  const upsertNote = useCallback((incoming: Note) => {
    if (incoming.is_on_hold) {
      // Route to on-hold list
      setOnHoldNotes((current) => current.some((n) => n.id === incoming.id)
        ? current.map((n) => n.id === incoming.id ? incoming : n)
        : [incoming, ...current]);
      // Remove from active notes and links
      setNotes((current) => current.filter((n) => n.id !== incoming.id));
      setLinks((current) => current.filter((l) => l.id !== incoming.id));
    } else if (incoming.kind === 'file') {
      // Remove from notes, links, and on-hold
      setNotes((current) => current.filter((n) => n.id !== incoming.id));
      setLinks((current) => current.filter((l) => l.id !== incoming.id));
      setOnHoldNotes((current) => current.filter((n) => n.id !== incoming.id));
    } else if (incoming.kind === 'link') {
      // Route to links list
      setLinks((current) => current.some((l) => l.id === incoming.id)
        ? current.map((l) => l.id === incoming.id ? incoming : l)
        : [incoming, ...current]);
      // Remove from notes and on-hold
      setNotes((current) => current.filter((n) => n.id !== incoming.id));
      setOnHoldNotes((current) => current.filter((n) => n.id !== incoming.id));
    } else {
      // Route to notes list
      setNotes((current) => current.some((n) => n.id === incoming.id)
        ? current.map((n) => n.id === incoming.id ? incoming : n)
        : [incoming, ...current]);
      // Remove from links and on-hold
      setLinks((current) => current.filter((l) => l.id !== incoming.id));
      setOnHoldNotes((current) => current.filter((n) => n.id !== incoming.id));
    }
  }, []);

  // Fetch notes
  useEffect(() => {
    let active = true;
    notesApi.list('note')
      .then((result) => active && setNotes(result))
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  // Fetch links
  useEffect(() => {
    let active = true;
    notesApi.list('link')
      .then((result) => active && setLinks(result))
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  // Fetch on-hold notes
  useEffect(() => {
    let active = true;
    notesApi.list('note', true)
      .then((result) => active && setOnHoldNotes(result))
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      notesApi.status()
        .then((result) => active && setTelegram(result.telegram))
        .catch(() => undefined);
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | undefined;
    let heartbeat: number | undefined;

    const connect = () => {
      if (disposed) return;
      setConnection('connecting');
      socket = new WebSocket(websocketUrl());
      socket.onopen = () => {
        setConnection('connected');
        heartbeat = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send('ping');
        }, 20_000);
      };
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as NoteEvent;
        if (event.type === 'note.deleted') {
          setNotes((current) => current.filter((note) => note.id !== event.id));
          setLinks((current) => current.filter((link) => link.id !== event.id));
          setOnHoldNotes((current) => current.filter((note) => note.id !== event.id));
          setActiveThread((current) => current?.id === event.id ? null : current);
        } else if (event.type === 'note.created' || event.type === 'note.updated') {
          upsertNote(event.note);
        } else if (event.type === 'thread.created' || event.type === 'thread.deleted') {
          setNotes((current) =>
            current.map((note) =>
              note.id === event.note_id ? { ...note, thread_count: event.thread_count } : note
            )
          );
        }
      };
      socket.onclose = () => {
        if (heartbeat) window.clearInterval(heartbeat);
        if (!disposed) {
          setConnection('offline');
          reconnectTimer.current = window.setTimeout(connect, 2500);
        }
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      disposed = true;
      if (heartbeat) window.clearInterval(heartbeat);
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      socket?.close();
    };
  }, [upsertNote]);

  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return needle ? notes.filter((note) => note.content.toLocaleLowerCase().includes(needle)) : notes;
  }, [notes, search]);

  const pinned = newestFirst(visible.filter((note) => note.is_pinned && !note.is_done));
  const inbox = newestFirst(visible.filter((note) => !note.is_pinned && !note.is_done));
  const done = newestFirst(visible.filter((note) => note.is_done));
  const openCount = notes.filter((note) => !note.is_done).length;

  async function addNote(event?: React.SyntheticEvent, editorValue?: RichTextChange) {
    event?.preventDefault();
    const rawText = (editorValue?.plainText ?? draft).trim();
    const hasRichContent = editorValue ? !editorValue.isEmpty : Boolean(rawText);
    const content = rawText || (hasRichContent ? 'Rich note' : '');
    const document = hasRichContent ? (editorValue?.document ?? draftDocument) : null;
    if ((!content && files.length === 0) || saving) return;
    const finalContent = content || '📎 Attachment';
    setSaving(true);
    setError('');
    try {
      const created = await notesApi.create(
        finalContent,
        files.length > 0 ? files : undefined,
        document,
      );
      upsertNote(created);
      setDraft('');
      setDraftDocument(null);
      setFiles([]);

      // If the note was classified as a link, show a toast
      if (created.kind === 'link') {
        setLinkToast(true);
        if (linkToastTimer.current) window.clearTimeout(linkToastTimer.current);
        linkToastTimer.current = window.setTimeout(() => setLinkToast(false), 2500);
      }

      notesApi.status()
        .then((status) => setTelegram(status.telegram))
        .catch(() => undefined);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not add note');
    } finally {
      setSaving(false);
    }
  }

  async function updateNote(note: Note, update: NoteUpdate) {
    setBusyIds((current) => new Set(current).add(note.id));
    setError('');
    try {
      upsertNote(await notesApi.update(note.id, update));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update note');
    } finally {
      setBusyIds((current) => {
        const next = new Set(current);
        next.delete(note.id);
        return next;
      });
    }
  }

  async function deleteNote(note: Note) {
    setBusyIds((current) => new Set(current).add(note.id));
    setError('');
    try {
      await notesApi.remove(note.id);
      setNotes((current) => current.filter((item) => item.id !== note.id));
      setLinks((current) => current.filter((item) => item.id !== note.id));
      setOnHoldNotes((current) => current.filter((item) => item.id !== note.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not delete note');
    } finally {
      setBusyIds((current) => {
        const next = new Set(current);
        next.delete(note.id);
        return next;
      });
    }
  }

  function handleOpenThread(note: Note) {
    setActiveThread(note);
  }

  const handleThreadCountChange = useCallback((noteId: number, count: number) => {
    setNotes((current) =>
      current.map((note) =>
        note.id === noteId ? { ...note, thread_count: count } : note
      )
    );
  }, []);

  function handleViewChange(newView: View) {
    setView(newView);
    setActiveThread(null);
  }

  // Drag-and-drop file handling on the composer
  function handleDragEnter(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes('Files')) {
      setDragOver(true);
    }
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }

  function handleDragOverEvent(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const maxSize = 50 * 1024 * 1024;
      const newFiles = Array.from(e.dataTransfer.files).filter((f) => {
        if (f.size > maxSize) {
          alert(`"${f.name}" is too large (max 50 MB)`);
          return false;
        }
        return f.size > 0;
      });
      setFiles((prev) => [...prev, ...newFiles]);
    }
  }

  const renderSortableList = (list: Note[], title: string) => {
    if (list.length === 0) return null;
    return (
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={(e) => handleDragEnd(e, list)}>
        <Section title={title} count={list.length}>
          <SortableContext items={list.map((n) => n.id)} strategy={verticalListSortingStrategy}>
            {list.map((note) => (
              <SortableNoteRow
                key={note.id}
                note={note}
                busy={busyIds.has(note.id)}
                onUpdate={(item, update) => void updateNote(item, update)}
                onDelete={(item) => void deleteNote(item)}
                onOpenThread={handleOpenThread}
              />
            ))}
          </SortableContext>
        </Section>
      </DndContext>
    );
  };

  const telegramLabel = !telegram
    ? 'Checking Telegram…'
    : !telegram.configured
      ? 'Telegram not configured'
      : !telegram.target_ready
        ? 'Send the bot a message to pair'
        : telegram.last_error
          ? telegram.last_error
          : 'Telegram connected';
  const telegramOk = telegram?.configured && telegram.target_ready && !telegram.last_error;

  // Determine what content to show
  const showComposer = view === 'notes' && !activeThread;

  return (
    <div className="app-shell">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header-inner">
          <div className="header-left">
            <h1 className="header-title">Pocketing</h1>
            <span className="header-count">
              {openCount === 0 ? 'Clear' : openCount}
            </span>
          </div>

          <div className="header-right">
            <div
              title={connection === 'connected' ? 'Live updates connected' : 'Reconnecting…'}
              className={`live-indicator ${connection === 'connected' ? 'connected' : 'offline'}`}
            >
              <span className="live-dot" />
              {connection === 'connected' ? 'Live' : 'Offline'}
            </div>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* ── Main layout: content + nav rail ── */}
      <div className="app-body">
        {/* ── Content ── */}
        <div className="app-main">
          {view === 'files' ? (
            <FilesView
              onBack={() => setView('notes')}
              onGoToNote={(noteId) => {
                setView('notes');
                // Find the note and open its thread, or just scroll to it
                const target = notes.find((n) => n.id === noteId);
                if (target) setActiveThread(target);
              }}
            />
          ) : view === 'links' ? (
            <LinksView
              links={links}
              busyIds={busyIds}
              onUpdate={(item, update) => void updateNote(item, update)}
              onDelete={(item) => void deleteNote(item)}
            />
          ) : view === 'onhold' ? (
            <OnHoldView
              onHoldNotes={onHoldNotes}
              busyIds={busyIds}
              onUpdate={(item, update) => void updateNote(item, update)}
              onDelete={(item) => void deleteNote(item)}
              onOpenThread={handleOpenThread}
            />
          ) : activeThread ? (
            <ThreadView
              note={activeThread}
              onBack={() => setActiveThread(null)}
              onThreadCountChange={handleThreadCountChange}
            />
          ) : (
            <div className="content-area">
              <div className="content-inner">
                {/* Search */}
                <div className="search-bar">
                  <SearchIcon size={13} className="search-icon" />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search…"
                    aria-label="Search notes"
                  />
                  {search && (
                    <button
                      type="button"
                      onClick={() => setSearch('')}
                      aria-label="Clear search"
                      className="search-clear"
                    >
                      <XIcon size={12} />
                    </button>
                  )}
                </div>

                {/* Error */}
                {error && <div className="error-banner">{error}</div>}

                {/* Link toast */}
                {linkToast && (
                  <div className="link-toast">Moved to Links</div>
                )}

                {/* Notes */}
                {loading ? (
                  <div className="loading-spinner">
                    <div className="spinner" />
                  </div>
                ) : (
                  <>
                    {renderSortableList(pinned, 'Pinned')}
                    {renderSortableList(inbox, 'Inbox')}
                    <Section title="Done" count={done.length}>
                      {done.map((note) => (
                        <NoteRow
                          key={note.id}
                          note={note}
                          busy={busyIds.has(note.id)}
                          onUpdate={(item, update) => void updateNote(item, update)}
                          onDelete={(item) => void deleteNote(item)}
                          onOpenThread={handleOpenThread}
                        />
                      ))}
                    </Section>

                    {visible.length === 0 && (
                      <div className="empty-state">
                        <div className="empty-state-icon">
                          {search ? <SearchIcon size={20} /> : <CheckIcon size={20} />}
                        </div>
                        <p className="empty-state-title">{search ? 'No results' : 'All clear'}</p>
                        <p className="empty-state-sub">{search ? 'Try a different search' : 'Notes you send will appear here'}</p>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {/* ── Composer ── */}
          {showComposer && <div
            className={`composer${dragOver ? ' drag-over' : ''}`}
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={handleDragOverEvent}
            onDrop={handleDrop}
          >
            <div className="composer-inner">
              <form onSubmit={(event) => void addNote(event)} className="composer-form">
                <RichTextEditor
                  autoFocus
                  document={draftDocument}
                  plainText={draft}
                  onChange={({ document, plainText, isEmpty }: RichTextChange) => {
                    setDraftDocument(document);
                    setDraft(isEmpty ? '' : (plainText || 'Rich note'));
                  }}
                  onSubmit={(value) => void addNote(undefined, value)}
                  placeholder="Write a note, idea, task, or anything worth keeping…"
                  maxLength={4000}
                  ariaLabel="New note"
                  footer={
                    <>
                      <div className="editor-footer-start">
                        <FileUploadButton files={files} onChange={setFiles} />
                        <span className="editor-shortcut">Ctrl+Enter to send</span>
                      </div>
                      <button
                        type="submit"
                        disabled={(!draft.trim() && files.length === 0) || saving}
                        aria-label={saving ? 'Sending note' : 'Send note'}
                        title="Save and send to Telegram"
                        className="composer-send"
                      >
                        {saving ? <span className="spin">↻</span> : <SendIcon size={17} />}
                      </button>
                    </>
                  }
                />
              </form>

              <div className={`app-footer ${telegramOk ? 'status-ok' : 'status-warn'}`}>
                {telegramLabel}
              </div>
            </div>
          </div>}
        </div>

        {/* ── Nav Rail ── */}
        <NavRail view={activeThread ? 'notes' : view} onViewChange={handleViewChange} onHoldCount={onHoldNotes.length} />
      </div>
    </div>
  );
}
