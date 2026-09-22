import { useEffect, useMemo, useRef, useState } from 'react';

import {
  CheckIcon,
  CopyIcon,
  LinkIcon,
  PinIcon,
  SearchIcon,
  TrashIcon,
  XIcon,
} from '@/components/Icons';
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

function extractDomain(url: string): string {
  try {
    return new URL(url.trim()).hostname.replace(/^www\./, '');
  } catch {
    return url.trim();
  }
}

function newestFirst(list: Note[]): Note[] {
  return [...list].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

interface LinksViewProps {
  links: Note[];
  busyIds: Set<number>;
  onUpdate: (note: Note, update: NoteUpdate) => void;
  onDelete: (note: Note) => void;
}

export function LinksView({ links, busyIds, onUpdate, onDelete }: LinksViewProps) {
  const [search, setSearch] = useState('');
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const copyTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => {
    if (copyTimer.current) window.clearTimeout(copyTimer.current);
  }, []);

  async function copyLink(link: Note) {
    const url = link.content.trim();
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        // Fallback for older browsers / insecure context
        const textarea = document.createElement('textarea');
        textarea.value = url;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      setCopiedId(link.id);
      if (copyTimer.current) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopiedId(null), 1500);
    } catch {
      setCopiedId(null);
    }
  }

  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    if (!needle) return links;
    return links.filter((link) => {
      const url = link.content.toLocaleLowerCase();
      const domain = extractDomain(link.content).toLocaleLowerCase();
      return url.includes(needle) || domain.includes(needle);
    });
  }, [links, search]);

  const pinned = newestFirst(visible.filter((l) => l.is_pinned));
  const unpinned = newestFirst(visible.filter((l) => !l.is_pinned));

  const renderCard = (link: Note) => {
    const url = link.content.trim();
    const domain = extractDomain(url);
    const isCopied = copiedId === link.id;
    const busy = busyIds.has(link.id);

    return (
      <article key={link.id} className="link-row">
        <div className="link-card">
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="link-card-url"
            onClick={(e) => e.stopPropagation()}
          >
            {url}
          </a>
          <div className="link-card-meta">
            <span className="link-card-domain">{domain}</span>
            <span>·</span>
            <span>{relativeTime(link.created_at)}</span>
            {link.is_pinned && (
              <span className="pin-badge">
                · <PinIcon size={9} fill="currentColor" /> pinned
              </span>
            )}
          </div>
        </div>

        <div className="note-actions">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); void copyLink(link); }}
            aria-label={isCopied ? 'Copied' : 'Copy link'}
            title={isCopied ? 'Copied!' : 'Copy'}
            className={`note-action-btn${isCopied ? ' copy-confirmed' : ''}`}
          >
            {isCopied ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onUpdate(link, { is_pinned: !link.is_pinned }); }}
            disabled={busy}
            aria-label={link.is_pinned ? 'Unpin' : 'Pin'}
            title={link.is_pinned ? 'Unpin' : 'Pin'}
            className={`note-action-btn${link.is_pinned ? ' pin-active' : ''}`}
          >
            <PinIcon size={13} fill={link.is_pinned ? 'currentColor' : 'none'} />
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onDelete(link); }}
            disabled={busy}
            aria-label="Delete link"
            title="Delete"
            className="note-action-btn danger"
          >
            <TrashIcon size={13} />
          </button>
        </div>
      </article>
    );
  };

  return (
    <div className="content-area">
      <div className="content-inner">
        {/* Search */}
        <div className="search-bar">
          <SearchIcon size={13} className="search-icon" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search links…"
            aria-label="Search links"
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

        {/* Pinned */}
        {pinned.length > 0 && (
          <section className="section">
            <div className="section-header">
              <span className="section-label">Pinned</span>
              <span className="section-count">{pinned.length}</span>
            </div>
            {pinned.map(renderCard)}
          </section>
        )}

        {/* Links */}
        {unpinned.length > 0 && (
          <section className="section">
            <div className="section-header">
              <span className="section-label">Links</span>
              <span className="section-count">{unpinned.length}</span>
            </div>
            {unpinned.map(renderCard)}
          </section>
        )}

        {/* Empty */}
        {visible.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">
              {search ? <SearchIcon size={20} /> : <LinkIcon size={20} />}
            </div>
            <p className="empty-state-title">{search ? 'No results' : 'No links yet'}</p>
            <p className="empty-state-sub">
              {search ? 'Try a different search' : "Send a link and it'll land here."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
