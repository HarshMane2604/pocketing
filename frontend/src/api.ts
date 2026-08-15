import type { Note, NoteUpdate, RuntimeStatus } from '@/types';

const configuredUrl = import.meta.env.VITE_API_URL?.replace(/\/$/, '');
const apiUrl = configuredUrl ?? '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const notesApi = {
  list: () => request<Note[]>('/api/notes'),
  status: () => request<RuntimeStatus>('/api/status'),
  create: (content: string) => request<Note>('/api/notes', {
    method: 'POST',
    body: JSON.stringify({ content }),
  }),
  update: (id: number, update: NoteUpdate) => request<Note>(`/api/notes/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(update),
  }),
  remove: (id: number) => request<void>(`/api/notes/${id}`, { method: 'DELETE' }),
  reorder: (noteIds: number[]) => request<void>('/api/notes/reorder', {
    method: 'PUT',
    body: JSON.stringify({ note_ids: noteIds }),
  }),
};

export function websocketUrl(): string {
  if (configuredUrl) {
    const url = new URL(configuredUrl);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = '/ws';
    url.search = '';
    return url.toString();
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}
