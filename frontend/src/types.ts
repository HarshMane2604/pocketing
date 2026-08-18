export interface Note {
  id: number;
  content: string;
  created_at: string;
  is_pinned: boolean;
  is_done: boolean;
  source: 'web' | 'telegram';
  priority: number;
  thread_count: number;
}

export interface ThreadMessage {
  id: number;
  note_id: number;
  content: string;
  created_at: string;
}

export type NoteUpdate = Partial<Pick<Note, 'content' | 'is_pinned' | 'is_done' | 'priority'>>;

export type NoteEvent =
  | { type: 'note.created' | 'note.updated'; note: Note }
  | { type: 'note.deleted'; id: number }
  | { type: 'thread.created'; message: ThreadMessage; note_id: number; thread_count: number }
  | { type: 'thread.deleted'; message_id: number; note_id: number; thread_count: number };

export interface TelegramStatus {
  configured: boolean;
  running: boolean;
  chat_restricted: boolean;
  target_ready: boolean;
  last_error: string | null;
  last_message_at: string | null;
  last_sent_at: string | null;
}

export interface RuntimeStatus {
  status: string;
  telegram: TelegramStatus;
}
