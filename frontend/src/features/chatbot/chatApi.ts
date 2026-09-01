import { requestJson } from '../../shared/api/httpClient';
import type {
  ChatAttachment,
  ChatMessage,
  ChatSession,
  ChatTurn,
} from './types';

export const chatApi = {
  list(clientId: string) {
    return requestJson<{ sessions: ChatSession[] }>(
      `/api/chat/sessions?client_id=${encodeURIComponent(clientId)}`,
    );
  },
  suggestions() {
    return requestJson<{ questions: string[] }>('/api/chat/suggestions');
  },
  refreshSuggestions() {
    return requestJson<{ questions: string[] }>('/api/chat/suggestions/refresh', { method: 'POST' });
  },
  create(clientId: string, signal?: AbortSignal) {
    return requestJson<ChatSession>('/api/chat/sessions', {
      method: 'POST',
      json: { client_id: clientId },
      signal,
    });
  },
  get(sessionId: string, clientId: string, signal?: AbortSignal) {
    return requestJson<ChatSession>(
      `/api/chat/sessions/${encodeURIComponent(sessionId)}?client_id=${encodeURIComponent(clientId)}`,
      { signal },
    );
  },
  rename(sessionId: string, clientId: string, title: string) {
    return requestJson<ChatSession>(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      json: { client_id: clientId, title },
    });
  },
  remove(sessionId: string, clientId: string) {
    return requestJson<{ deleted: string }>(
      `/api/chat/sessions/${encodeURIComponent(sessionId)}?client_id=${encodeURIComponent(clientId)}`,
      { method: 'DELETE' },
    );
  },
  upload(
    sessionId: string,
    clientId: string,
    file: File,
    signal?: AbortSignal,
  ) {
    const body = new FormData();
    body.set('client_id', clientId);
    body.set('file', file);
    return requestJson<ChatAttachment>(
      `/api/chat/sessions/${encodeURIComponent(sessionId)}/attachments`,
      { method: 'POST', body, timeout: 60_000, signal },
    );
  },
  send(
    sessionId: string,
    clientId: string,
    content: string,
    attachmentId?: string,
    signal?: AbortSignal,
  ) {
    return requestJson<{
      user_message: ChatMessage;
      assistant_message: ChatMessage;
      run_id: string | null;
      mode: 'direct' | 'rag';
    }>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
      method: 'POST',
      json: { client_id: clientId, content, attachment_id: attachmentId },
      timeout: 45_000,
      signal,
    });
  },
  sync(runId: string, clientId: string, signal?: AbortSignal) {
    return requestJson<ChatTurn>(
      `/api/chat/runs/${encodeURIComponent(runId)}?client_id=${encodeURIComponent(clientId)}`,
      { signal },
    );
  },
};
