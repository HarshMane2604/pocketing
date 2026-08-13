export interface Note {
  id: number;
  content: string;
  created_at: string;
  is_pinned: boolean;
  is_done: boolean;
}

export type NoteUpdate = Partial<Pick<Note, 'content' | 'is_pinned' | 'is_done'>>;

export type NoteEvent =
  | { type: 'note.created' | 'note.updated'; note: Note }
  | { type: 'note.deleted'; id: number };

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
