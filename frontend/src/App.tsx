import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';

import { notesApi, websocketUrl } from '@/api';
import { CheckIcon, SearchIcon, XIcon } from '@/components/Icons';
import { NoteRow } from '@/components/NoteRow';
import { ThemeToggle } from '@/components/ThemeToggle';
import type { Note, NoteEvent, NoteUpdate, TelegramStatus } from '@/types';

type ConnectionState = 'connecting' | 'connected' | 'offline';

function newestFirst(notes: Note[]): Note[] {
  return [...notes].sort((a, b) => {
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
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyIds, setBusyIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState('');
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null);
  const reconnectTimer = useRef<number | undefined>(undefined);

  const upsert = useCallback((incoming: Note) => {
    setNotes((current) => current.some((note) => note.id === incoming.id)
      ? current.map((note) => note.id === incoming.id ? incoming : note)
      : [incoming, ...current]);
  }, []);

  useEffect(() => {
    let active = true;
    notesApi.list()
      .then((result) => active && setNotes(result))
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
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
        } else {
          upsert(event.note);
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
  }, [upsert]);

  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return needle ? notes.filter((note) => note.content.toLocaleLowerCase().includes(needle)) : notes;
  }, [notes, search]);

  const pinned = newestFirst(visible.filter((note) => note.is_pinned && !note.is_done));
  const inbox = newestFirst(visible.filter((note) => !note.is_pinned && !note.is_done));
  const done = newestFirst(visible.filter((note) => note.is_done));
  const openCount = notes.filter((note) => !note.is_done).length;

  async function addNote(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || saving) return;
    setSaving(true);
    setError('');
    try {
      const created = await notesApi.create(content);
      upsert(created);
      setDraft('');
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
      upsert(await notesApi.update(note.id, update));
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

  const renderNote = (note: Note) => (
    <NoteRow
      key={note.id}
      note={note}
      busy={busyIds.has(note.id)}
      onUpdate={(item, update) => void updateNote(item, update)}
      onDelete={(item) => void deleteNote(item)}
    />
  );

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

      {/* ── Content ── */}
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

          {/* Notes */}
          {loading ? (
            <div className="loading-spinner">
              <div className="spinner" />
            </div>
          ) : (
            <>
              <Section title="Pinned" count={pinned.length}>{pinned.map(renderNote)}</Section>
              <Section title="Inbox" count={inbox.length}>{inbox.map(renderNote)}</Section>
              <Section title="Done" count={done.length}>{done.map(renderNote)}</Section>

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

      {/* ── Composer ── */}
      <div className="composer">
        <div className="composer-inner">
          <form onSubmit={(event) => void addNote(event)} className="composer-row">
            <input
              autoFocus
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Write a note…"
              maxLength={4000}
              aria-label="New note"
              className="composer-input"
            />
            <button
              type="submit"
              disabled={!draft.trim() || saving}
              aria-label="Send"
              title="Save and send to Telegram"
              className="composer-send"
            >
              {saving ? <span className="spin">↻</span> : 'Send'}
            </button>
          </form>

          <div className={`app-footer ${telegramOk ? 'status-ok' : 'status-warn'}`}>
            {telegramLabel}
          </div>
        </div>
      </div>
    </div>
  );
}
