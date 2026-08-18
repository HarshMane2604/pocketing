import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

import { threadApi } from '@/api';
import { ArrowLeftIcon, CheckIcon, CopyIcon, TrashIcon } from '@/components/Icons';
import type { Note, ThreadMessage } from '@/types';

function relativeTime(value: string): string {
  const date = new Date(value);
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return 'now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d`;
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date);
}

interface ThreadViewProps {
  note: Note;
  onBack: () => void;
  onThreadCountChange: (noteId: number, count: number) => void;
}

export function ThreadView({ note, onBack, onThreadCountChange }: ThreadViewProps) {
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const listRef = useRef<HTMLDivElement>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const copyTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let active = true;
    threadApi.list(note.id)
      .then((result) => {
        if (active) {
          setMessages(result);
          onThreadCountChange(note.id, result.length);
        }
      })
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [note.id, onThreadCountChange]);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => () => {
    if (copyTimer.current) window.clearTimeout(copyTimer.current);
  }, []);

  async function copyMessage(id: number, content: string) {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      if (copyTimer.current) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopiedId(null), 1400);
    } catch {
      setCopiedId(null);
    }
  }

  async function addMessage(event?: React.SyntheticEvent) {
    event?.preventDefault();
    const content = draft.trim();
    if (!content || sending) return;
    setSending(true);
    setError('');
    try {
      const created = await threadApi.create(note.id, content);
      setMessages((current) => [...current, created]);
      setDraft('');
      onThreadCountChange(note.id, messages.length + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not add message');
    } finally {
      setSending(false);
    }
  }

  async function deleteMessage(messageId: number) {
    setError('');
    try {
      await threadApi.remove(note.id, messageId);
      setMessages((current) => {
        const next = current.filter((m) => m.id !== messageId);
        onThreadCountChange(note.id, next.length);
        return next;
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not delete message');
    }
  }

  // This is called from App.tsx when a WebSocket thread event arrives
  // for this note. We expose addMessageFromWs and removeMessageFromWs
  // via the parent callbacks instead.

  const preview = note.content.length > 80
    ? note.content.slice(0, 80) + '…'
    : note.content;

  return (
    <div className="thread-view">
      {/* Thread Header */}
      <div className="thread-header">
        <button type="button" onClick={onBack} className="thread-back-btn" aria-label="Back to notes">
          <ArrowLeftIcon size={16} />
        </button>
        <div className="thread-header-info">
          <span className="thread-header-label">Thread</span>
          <p className="thread-header-note">{preview}</p>
        </div>
      </div>

      {/* Messages */}
      <div className="thread-messages" ref={listRef}>
        {error && <div className="error-banner">{error}</div>}

        {loading ? (
          <div className="loading-spinner">
            <div className="spinner" />
          </div>
        ) : messages.length === 0 ? (
          <div className="empty-state">
            <p className="empty-state-title">No messages yet</p>
            <p className="empty-state-sub">Add a message to start tracking info for this note</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className="thread-message">
              <div className="thread-message-bubble">
                <div className="thread-message-content prose prose-sm dark:prose-invert break-words max-w-none custom-prose">
                  <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{msg.content}</ReactMarkdown>
                </div>
                <span className="thread-message-time">{relativeTime(msg.created_at)}</span>
              </div>
              <div className="thread-message-actions">
                <button
                  type="button"
                  onClick={() => void copyMessage(msg.id, msg.content)}
                  aria-label={copiedId === msg.id ? 'Message copied' : 'Copy message'}
                  title={copiedId === msg.id ? 'Copied' : 'Copy'}
                  className={`thread-message-action-btn${copiedId === msg.id ? ' copy-confirmed' : ''}`}
                >
                  {copiedId === msg.id ? <CheckIcon size={12} /> : <CopyIcon size={12} />}
                </button>
                <button
                  type="button"
                  onClick={() => void deleteMessage(msg.id)}
                  aria-label="Delete message"
                  title="Delete"
                  className="thread-message-action-btn delete-btn"
                >
                  <TrashIcon size={12} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Composer */}
      <div className="thread-composer">
        <form onSubmit={(event) => void addMessage(event)} className="composer-row">
          <textarea
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void addMessage();
              }
            }}
            placeholder="Add to thread…"
            maxLength={4000}
            aria-label="New thread message"
            className="composer-input"
            rows={1}
            style={{ resize: 'none' }}
          />
          <button
            type="submit"
            disabled={!draft.trim() || sending}
            aria-label="Send"
            className="composer-send"
          >
            {sending ? <span className="spin">↻</span> : 'Send'}
          </button>
        </form>
      </div>
    </div>
  );
}
