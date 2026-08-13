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
  const cls = [
    'note-row',
    `source-${note.source || 'web'}`,
    note.is_pinned && !note.is_done ? 'pinned' : '',
    note.is_done ? 'done' : '',
  ].filter(Boolean).join(' ');

  return (
    <article className={cls}>
      <button
        type="button"
        onClick={() => onUpdate(note, { is_done: !note.is_done })}
        disabled={busy}
        aria-label={note.is_done ? 'Move back to inbox' : 'Mark done'}
        title={note.is_done ? 'Move back to inbox' : 'Mark done'}
        className="note-check"
      >
        {note.is_done ? <CheckIcon size={15} /> : <CircleIcon size={15} />}
      </button>

      <div className="note-bubble">
        <p className={`note-content${note.is_done ? ' done-text' : ''}`}>
          {note.content}
        </p>
        <div className="note-meta">
          <span>{relativeTime(note.created_at)}</span>
          {note.is_pinned && (
            <span className="pin-badge">
              · <PinIcon size={9} fill="currentColor" /> pinned
            </span>
          )}
        </div>
      </div>

      <div className="note-actions">
        <button
          type="button"
          onClick={() => onUpdate(note, { is_pinned: !note.is_pinned })}
          disabled={busy}
          aria-label={note.is_pinned ? 'Unpin note' : 'Pin note'}
          title={note.is_pinned ? 'Unpin' : 'Pin'}
          className={`note-action-btn${note.is_pinned ? ' pin-active' : ''}`}
        >
          <PinIcon size={13} fill={note.is_pinned ? 'currentColor' : 'none'} />
        </button>
        <button
          type="button"
          onClick={() => onDelete(note)}
          disabled={busy}
          aria-label="Delete note"
          title="Delete"
          className="note-action-btn danger"
        >
          <TrashIcon size={13} />
        </button>
      </div>
    </article>
  );
}
