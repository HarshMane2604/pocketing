import { useEffect, useRef, useState } from 'react';
import type { JSONContent } from '@tiptap/core';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

import { CheckIcon, CircleIcon, CopyIcon, PinIcon, ThreadIcon, TrashIcon } from '@/components/Icons';
import { AttachmentPreview } from '@/components/AttachmentPreview';
import { RichTextDisplay } from '@/components/RichTextDisplay';
import { RichTextEditor, type RichTextChange } from '@/components/RichTextEditor';
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

function normalizeLegacyMarkdown(value: string): string {
  return value.replace(/\*\*([^*\n]*?\S)\s+\*\*/g, '**$1** ');
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
  const [editDocument, setEditDocument] = useState<JSONContent | null>(note.structured_content);
  const [copied, setCopied] = useState(false);
  const [clock, setClock] = useState(() => Date.now());
  const copyTimer = useRef<number | undefined>(undefined);

  const editableUntil = new Date(note.editable_until).getTime();
  const canEdit = note.can_edit
    && note.source === 'web'
    && Number.isFinite(editableUntil)
    && clock < editableUntil;
  const editMinutesRemaining = canEdit
    ? Math.max(1, Math.ceil((editableUntil - clock) / 60_000))
    : 0;
  const editTitle = canEdit
    ? note.telegram_sync_available
      ? `Click to edit (${editMinutesRemaining}m remaining; Telegram will sync)`
      : `Click to edit (${editMinutesRemaining}m remaining; Telegram sync unavailable)`
    : note.source === 'telegram'
      ? 'Telegram messages cannot be edited from Pocketing'
      : 'The 15-minute edit window has expired';
  
  const tags = [...new Set(Array.from(note.content.matchAll(/(?:^|\s)#([a-zA-Z0-9_-]+)/g)).map(m => m[1]))];
  const displayContent = note.content.replace(/(?:^|\s)#[a-zA-Z0-9_-]+/g, '').trim() || note.content;
  const renderedContent = normalizeLegacyMarkdown(displayContent);

  const cls = [
    'note-row',
    `source-${note.source || 'web'}`,
    note.is_pinned && !note.is_done ? 'pinned' : '',
    note.is_done ? 'done' : '',
    isDragging ? 'is-dragging' : '',
  ].filter(Boolean).join(' ');

  useEffect(() => {
    if (!editing) {
      setEditContent(note.content);
      setEditDocument(note.structured_content);
    }
  }, [editing, note.content, note.structured_content]);

  useEffect(() => () => {
    if (copyTimer.current) window.clearTimeout(copyTimer.current);
  }, []);

  useEffect(() => {
    setClock(Date.now());
    if (!note.can_edit || !Number.isFinite(editableUntil)) return;

    const interval = window.setInterval(() => setClock(Date.now()), 30_000);
    const expiry = window.setTimeout(
      () => setClock(Date.now()),
      Math.max(0, editableUntil - Date.now()) + 50,
    );
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(expiry);
    };
  }, [editableUntil, note.can_edit]);

  useEffect(() => {
    if (editing && !canEdit) {
      setEditContent(note.content);
      setEditDocument(note.structured_content);
      setEditing(false);
    }
  }, [canEdit, editing, note.content, note.structured_content]);

  function startEditing() {
    if (busy || !canEdit) return;
    setEditContent(note.content);
    setEditDocument(note.structured_content);
    setEditing(true);
  }

  function finishEditing(editorValue?: RichTextChange) {
    const rawText = (editorValue?.plainText ?? editContent).trim();
    const content = rawText || (editorValue && !editorValue.isEmpty ? 'Rich note' : '');
    const document = editorValue?.document ?? editDocument;
    setEditing(false);
    const documentChanged = JSON.stringify(document) !== JSON.stringify(note.structured_content);
    if (content && (content !== note.content || documentChanged)) {
      onUpdate(note, { content, structured_content: document });
    }
    if (!content) {
      setEditContent(note.content);
      setEditDocument(note.structured_content);
    }
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
          <RichTextEditor
            autoFocus
            document={editDocument}
            plainText={editContent}
            onChange={({ document, plainText, isEmpty }: RichTextChange) => {
              setEditDocument(document);
              setEditContent(isEmpty ? '' : (plainText || 'Rich note'));
            }}
            onBlur={finishEditing}
            onCancel={() => {
              setEditContent(note.content);
              setEditDocument(note.structured_content);
              setEditing(false);
            }}
            onSubmit={finishEditing}
            maxLength={4000}
            placeholder="Edit note…"
            ariaLabel="Edit note"
            className="rich-editor--inline"
          />
        ) : (
          <div
            onClick={canEdit ? startEditing : undefined}
            title={editTitle}
            className={`note-content${canEdit ? ' editable' : ''} prose prose-sm dark:prose-invert break-words max-w-none custom-prose${note.is_done ? ' done-text' : ''}`}
          >
            {note.structured_content
              ? <RichTextDisplay content={note.structured_content} />
              : <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{renderedContent}</ReactMarkdown>}
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
          {canEdit && !editing && <span>· edit {editMinutesRemaining}m</span>}
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
