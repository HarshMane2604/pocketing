import type { JSONContent } from '@tiptap/core';
import type { FileSearchResult, Note, NoteUpdate, RuntimeStatus, ThreadMessage } from '@/types';

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

/** Like request() but without setting Content-Type (for FormData). */
async function requestRaw<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, options);

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
  create: (content: string, files?: File[], structuredContent?: JSONContent | null) => {
    const form = new FormData();
    form.append('content', content);
    if (structuredContent) form.append('structured_content', JSON.stringify(structuredContent));
    if (files) {
      for (const file of files) {
        form.append('files', file);
      }
    }
    return requestRaw<Note>('/api/notes', {
      method: 'POST',
      body: form,
    });
  },
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

export const threadApi = {
  list: (noteId: number) => request<ThreadMessage[]>(`/api/notes/${noteId}/thread`),
  create: (noteId: number, content: string, files?: File[], structuredContent?: JSONContent | null) => {
    const form = new FormData();
    form.append('content', content);
    if (structuredContent) form.append('structured_content', JSON.stringify(structuredContent));
    if (files) {
      for (const file of files) {
        form.append('files', file);
      }
    }
    return requestRaw<ThreadMessage>(`/api/notes/${noteId}/thread`, {
      method: 'POST',
      body: form,
    });
  },
  remove: (noteId: number, messageId: number) => request<void>(`/api/notes/${noteId}/thread/${messageId}`, {
    method: 'DELETE',
  }),
};

export const filesApi = {
  list: (params?: { search?: string; type?: string; sort?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.search) qs.set('search', params.search);
    if (params?.type) qs.set('type', params.type);
    if (params?.sort) qs.set('sort', params.sort);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return request<FileSearchResult[]>(`/api/files${query ? `?${query}` : ''}`);
  },
  delete: (fileId: number) => request<void>(`/api/files/${fileId}`, { method: 'DELETE' }),
  url: (relativeUrl: string) => `${apiUrl}${relativeUrl}`,
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
