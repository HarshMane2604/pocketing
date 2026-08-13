import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';

import { notesApi, websocketUrl } from '@/api';
import { CheckIcon, InboxIcon, SearchIcon, WifiIcon, XIcon } from '@/components/Icons';
import { NoteRow } from '@/components/NoteRow';
import type { Note, NoteEvent, NoteUpdate, TelegramStatus } from '@/types';

type ConnectionState = 'connecting' | 'connected' | 'offline';

function newestFirst(notes: Note[]): Note[] {
  return [...notes].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  if (!count) return null;
  return (
    <section className="mb-7">
      <div className="mb-2 flex items-center gap-2 px-1">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">{title}</h2>
        <span className="text-[11px] tabular-nums text-zinc-700">{count}</span>
      </div>
      <div className="overflow-hidden rounded-xl border border-white/[0.07] bg-[#111112]">{children}</div>
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
      ? 'Telegram is not configured'
      : !telegram.target_ready
        ? 'Send the bot one message to pair'
        : telegram.last_error
          ? telegram.last_error
          : 'Two-way Telegram connected';
  const telegramTone = telegram?.configured && telegram.target_ready && !telegram.last_error
    ? 'text-emerald-800'
    : 'text-amber-800';

  return (
    <main className="min-h-screen bg-[#090909] px-3 py-6 text-zinc-100 antialiased sm:py-10">
      <div className="mx-auto w-full max-w-[420px]">
        <header className="mb-6 flex items-start justify-between px-1">
          <div>
            <div className="flex items-center gap-2.5">
              <InboxIcon size={18} className="text-zinc-400" />
              <h1 className="text-[17px] font-semibold tracking-tight">Memory Inbox</h1>
            </div>
            <p className="mt-1.5 pl-[29px] text-xs text-zinc-600">
              {openCount === 0 ? 'Inbox clear' : `${openCount} open ${openCount === 1 ? 'note' : 'notes'}`}
            </p>
          </div>
          <div
            title={connection === 'connected' ? 'Live updates connected' : 'Live updates reconnecting'}
            className={`mt-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider ${
              connection === 'connected' ? 'text-emerald-700' : 'text-zinc-700'
            }`}
          >
            <WifiIcon size={12} /> {connection === 'connected' ? 'live' : 'offline'}
          </div>
        </header>

        <form onSubmit={(event) => void addNote(event)} className="mb-3 flex gap-2">
          <input
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Send a note to Telegram…"
            maxLength={4000}
            aria-label="New note"
            className="min-w-0 flex-1 rounded-xl border border-white/[0.08] bg-[#131314] px-3.5 py-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-700 focus:border-zinc-600"
          />
          <button
            type="submit"
            disabled={!draft.trim() || saving}
            aria-label="Save and send note"
            title="Save to inbox and send to Telegram"
            className="flex w-11 shrink-0 items-center justify-center rounded-xl border border-zinc-700 bg-zinc-100 text-lg text-zinc-950 transition hover:bg-white disabled:cursor-not-allowed disabled:border-white/[0.06] disabled:bg-[#151515] disabled:text-zinc-700"
          >
            {saving ? <span className="animate-spin text-sm">◌</span> : '+'}
          </button>
        </form>

        <div className="relative mb-7">
          <SearchIcon size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-700" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search notes"
            aria-label="Search notes"
            className="w-full rounded-lg border border-transparent bg-transparent py-2 pl-9 pr-8 text-xs text-zinc-300 outline-none placeholder:text-zinc-700 focus:border-white/[0.06] focus:bg-[#0f0f10]"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch('')}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-zinc-700 hover:text-zinc-300"
            >
              <XIcon size={13} />
            </button>
          )}
        </div>

        {error && <div className="mb-5 rounded-lg border border-red-950 bg-red-950/20 px-3 py-2 text-xs text-red-400">{error}</div>}

        {loading ? (
          <div className="flex justify-center py-16 text-zinc-700"><span className="animate-spin">◌</span></div>
        ) : (
          <>
            <Section title="Pinned" count={pinned.length}>{pinned.map(renderNote)}</Section>
            <Section title="Inbox" count={inbox.length}>{inbox.map(renderNote)}</Section>
            <Section title="Done" count={done.length}>{done.map(renderNote)}</Section>

            {visible.length === 0 && (
              <div className="flex flex-col items-center py-16 text-center">
                {search ? <SearchIcon size={22} className="mb-3 text-zinc-800" /> : <CheckIcon size={22} className="mb-3 text-zinc-800" />}
                <p className="text-sm text-zinc-600">{search ? 'No matching notes' : 'Nothing here'}</p>
                <p className="mt-1 text-xs text-zinc-800">{search ? 'Try another search' : 'Send a thought from here or Telegram'}</p>
              </div>
            )}
          </>
        )}

        <footer className={`mt-8 pb-3 text-center text-[10px] uppercase tracking-[0.14em] ${telegramTone}`}>
          {telegramLabel}
        </footer>
      </div>
    </main>
  );
}
