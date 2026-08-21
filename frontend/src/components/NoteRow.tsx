import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

import { CheckIcon, CircleIcon, CopyIcon, PinIcon, ThreadIcon, TrashIcon } from '@/components/Icons';
import { AttachmentPreview } from '@/components/AttachmentPreview';
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
  onOpenThread?: (note: Note) => void;
  dragHandleProps?: Record<string, any>;
  isDragging?: boolean;
}

export function NoteRow({ note, busy, onUpdate, onDelete, onOpenThread, dragHandleProps, isDragging }: NoteRowProps) {
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState(note.content);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | undefined>(undefined);
  
  const tags = [...new Set(Array.from(note.content.matchAll(/(?:^|\s)#([a-zA-Z0-9_-]+)/g)).map(m => m[1]))];
  const displayContent = note.content.replace(/(?:^|\s)#[a-zA-Z0-9_-]+/g, '').trim() || note.content;

  const cls = [
    'note-row',
    `source-${note.source || 'web'}`,
    note.is_pinned && !note.is_done ? 'pinned' : '',
    note.is_done ? 'done' : '',
    isDragging ? 'is-dragging' : '',
  ].filter(Boolean).join(' ');

  useEffect(() => {
    if (!editing) setEditContent(note.content);
  }, [editing, note.content]);

  useEffect(() => () => {
    if (copyTimer.current) window.clearTimeout(copyTimer.current);
  }, []);

  function startEditing() {
    if (busy) return;
    setEditContent(note.content);
    setEditing(true);
  }

  function finishEditing() {
    const content = editContent.trim();
    setEditing(false);
    if (content && content !== note.content) onUpdate(note, { content });
    if (!content) setEditContent(note.content);
  }

  async function copyNote() {
    try {
      await navigator.clipboard.writeText(note.content);
      setCopied(true);
      if (copyTimer.current) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className={cls} {...(editing ? {} : dragHandleProps)}>
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
        {tags.length > 0 && !editing && (
          <div className="note-tags">
            {tags.map(tag => {
              const lower = tag.toLowerCase();
              let displayTag = tag;
              if (lower === 'important') displayTag = 'imp';
              if (lower === 'urgent') displayTag = 'urg';
              if (lower === 'todo') displayTag = 'todo';
              if (lower === 'task') displayTag = 'task';
              
              return (
                <span key={tag} className={`note-tag tag-${lower}`}>
                  {displayTag}
                </span>
              );
            })}
          </div>
        )}
        {editing ? (
          <textarea
            autoFocus
            value={editContent}
            onChange={(event) => setEditContent(event.target.value)}
            onBlur={finishEditing}
            onPointerDown={(e) => e.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                setEditContent(note.content);
                setEditing(false);
              } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                finishEditing();
              }
            }}
            maxLength={4000}
            aria-label="Edit note"
            className="note-editor"
          />
        ) : (
          <div
            onClick={startEditing}
            title="Click to edit"
            className={`note-content editable prose prose-sm dark:prose-invert break-words max-w-none custom-prose${note.is_done ? ' done-text' : ''}`}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{displayContent}</ReactMarkdown>
          </div>
        )}

        {/* Attachment previews */}
        {note.attachments && note.attachments.length > 0 && (
          <AttachmentPreview attachments={note.attachments} />
        )}

        <div className="note-meta">
          <span>{relativeTime(note.created_at)}</span>
          {note.is_pinned && (
            <span className="pin-badge">
              · <PinIcon size={9} fill="currentColor" /> pinned
            </span>
          )}
          {editing && <span>· Ctrl+Enter to save</span>}
        </div>
      </div>

      <div className="note-actions">
        <button
          type="button"
          onClick={() => onOpenThread?.(note)}
          aria-label="Open thread"
          title="Thread"
          className={`note-action-btn${note.thread_count > 0 ? ' has-thread' : ''}`}
        >
          <ThreadIcon size={13} />
          {note.thread_count > 0 && (
            <span className="thread-count-badge">{note.thread_count}</span>
          )}
        </button>
        <button
          type="button"
          onClick={() => void copyNote()}
          aria-label={copied ? 'Note copied' : 'Copy note'}
          title={copied ? 'Copied' : 'Copy'}
          className={`note-action-btn${copied ? ' copy-confirmed' : ''}`}
        >
          {copied ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
        </button>
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
