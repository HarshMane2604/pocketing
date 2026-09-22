import { useMemo, useState } from 'react';

import { PauseIcon, SearchIcon, XIcon } from '@/components/Icons';
import { NoteRow } from '@/components/NoteRow';
import type { Note, NoteUpdate } from '@/types';

function newestFirst(list: Note[]): Note[] {
  return [...list].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

interface OnHoldViewProps {
  onHoldNotes: Note[];
  busyIds: Set<number>;
  onUpdate: (note: Note, update: NoteUpdate) => void;
  onDelete: (note: Note) => void;
  onOpenThread?: (note: Note) => void;
}

export function OnHoldView({ onHoldNotes, busyIds, onUpdate, onDelete, onOpenThread }: OnHoldViewProps) {
  const [search, setSearch] = useState('');

  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    if (!needle) return onHoldNotes;
    return onHoldNotes.filter((note) => note.content.toLocaleLowerCase().includes(needle));
  }, [onHoldNotes, search]);

  const sortedNotes = newestFirst(visible);

  return (
    <div className="content-area">
      <div className="content-inner">
        {/* Search */}
        <div className="search-bar">
          <SearchIcon size={13} className="search-icon" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search on hold items…"
            aria-label="Search on hold items"
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

        {/* On Hold List */}
        {sortedNotes.length > 0 && (
          <section className="section">
            <div className="section-header">
              <span className="section-label">On Hold</span>
              <span className="section-count">{sortedNotes.length}</span>
            </div>
            {sortedNotes.map((note) => (
              <NoteRow
                key={note.id}
                note={note}
                busy={busyIds.has(note.id)}
                onUpdate={onUpdate}
                onDelete={onDelete}
                onOpenThread={onOpenThread}
              />
            ))}
          </section>
        )}

        {/* Empty State */}
        {visible.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">
              {search ? <SearchIcon size={20} /> : <PauseIcon size={20} />}
            </div>
            <p className="empty-state-title">{search ? 'No results' : 'No items on hold'}</p>
            <p className="empty-state-sub">
              {search ? 'Try a different search' : 'Right-click any note to move it to On Hold.'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
