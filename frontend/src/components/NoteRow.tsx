import { CheckIcon, CircleIcon, PinIcon, TrashIcon } from '@/components/Icons';
import type { Note, NoteUpdate } from '@/types';

function relativeTime(value: string): string {
  const date = new Date(value);
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return 'now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d`;
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date);
}

interface NoteRowProps {
  note: Note;
  busy: boolean;
  onUpdate: (note: Note, update: NoteUpdate) => void;
  onDelete: (note: Note) => void;
}

export function NoteRow({ note, busy, onUpdate, onDelete }: NoteRowProps) {
  return (
    <article className="group flex gap-3 border-b border-white/[0.055] px-3 py-3.5 last:border-b-0 hover:bg-white/[0.025]">
      <button
        type="button"
        onClick={() => onUpdate(note, { is_done: !note.is_done })}
        disabled={busy}
        aria-label={note.is_done ? 'Move back to inbox' : 'Mark done'}
        title={note.is_done ? 'Move back to inbox' : 'Mark done'}
        className="mt-0.5 shrink-0 text-zinc-600 transition hover:text-zinc-200 disabled:opacity-40"
      >
        {note.is_done ? <CheckIcon size={17} /> : <CircleIcon size={17} />}
      </button>

      <div className="min-w-0 flex-1">
        <p className={`whitespace-pre-wrap break-words text-[14px] leading-[1.45] ${
          note.is_done ? 'text-zinc-600 line-through decoration-zinc-700' : 'text-zinc-200'
        }`}>
          {note.content}
        </p>
        <div className="mt-1.5 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-zinc-700">
          <span>{relativeTime(note.created_at)}</span>
          {note.is_pinned && <span>· pinned</span>}
        </div>
      </div>

      <div className="flex shrink-0 items-start gap-0.5 opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        <button
          type="button"
          onClick={() => onUpdate(note, { is_pinned: !note.is_pinned })}
          disabled={busy}
          aria-label={note.is_pinned ? 'Unpin note' : 'Pin note'}
          title={note.is_pinned ? 'Unpin' : 'Pin'}
          className={`rounded-md p-1.5 transition hover:bg-white/[0.06] disabled:opacity-40 ${
            note.is_pinned ? 'text-zinc-200' : 'text-zinc-600 hover:text-zinc-300'
          }`}
        >
          <PinIcon size={14} fill={note.is_pinned ? 'currentColor' : 'none'} />
        </button>
        <button
          type="button"
          onClick={() => onDelete(note)}
          disabled={busy}
          aria-label="Delete note"
          title="Delete"
          className="rounded-md p-1.5 text-zinc-700 transition hover:bg-red-950/30 hover:text-red-400 disabled:opacity-40"
        >
          <TrashIcon size={14} />
        </button>
      </div>
    </article>
  );
}
