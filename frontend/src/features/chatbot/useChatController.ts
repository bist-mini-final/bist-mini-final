import { useCallback, useEffect, useRef, useState } from 'react';
import { createUuid } from '../../shared/lib/uuid';
import { pipelineApi } from '../playground/services/api';
import { chatApi } from './chatApi';
import type {
  ChatDialogState,
  ChatMessage,
  ChatProgressStep,
  ChatSession,
} from './types';

export const DEFAULT_CHAT_EXAMPLES = [
  'IBM의 2024년과 2025년 매출을 비교해줘.',
  '2025년 IBM 총자산과 총부채는 각각 얼마인가?',
  'IBM의 현금흐름 추이를 차트로 보여줘.',
];

const CLIENT_KEY = 'rag-flow:chat-client-id';

function clientId(): string {
  let id = localStorage.getItem(CLIENT_KEY);
  if (!id) {
    id = createUuid();
    localStorage.setItem(CLIENT_KEY, id);
  }
  return id;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function progressForEvent(event: { event: string; data: unknown }): ChatProgressStep[] {
  if (event.event === 'run_started') {
    return [{ id: 'analysis', label: '질문을 분석하고 있습니다', state: 'active' }];
  }
  if (!event.event.startsWith('node_') || !event.data || typeof event.data !== 'object') return [];
  const node = event.data as { node_id?: string; module_type?: string; status?: string };
  if (node.status !== 'running') return [];
  const name = `${node.node_id ?? ''} ${node.module_type ?? ''}`.toLowerCase();
  const label = name.includes('embed')
    ? '질문을 벡터로 변환하고 있습니다'
    : name.includes('retriev') || name.includes('search') || name.includes('query')
      ? '관련 재무 문서를 검색하고 있습니다'
      : name.includes('rerank') || name.includes('fusion')
        ? '검색 결과의 관련도를 검토하고 있습니다'
        : name.includes('read') || name.includes('llm')
          ? '근거를 바탕으로 답변을 작성하고 있습니다'
          : '답변에 필요한 데이터를 처리하고 있습니다';
  return [{ id: node.node_id ?? name, label, state: 'active' }];
}

function replaceMessage(
  session: ChatSession,
  messageId: string,
  replacement: ChatMessage,
): ChatSession {
  return {
    ...session,
    messages: (session.messages ?? []).map((message) =>
      message.id === messageId ? replacement : message),
  };
}

/** Owns chat sessions, asynchronous runs, uploads, and dialog mutations. */
export function useChatController() {
  const [client] = useState(clientId);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [examples, setExamples] = useState(DEFAULT_CHAT_EXAMPLES);
  const [isRefreshingSuggestions, setIsRefreshingSuggestions] = useState(false);
  const [active, setActive] = useState<ChatSession | null>(null);
  const [draft, setDraft] = useState('');
  const [attachment, setAttachment] = useState<File | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [requestError, setRequestError] = useState('');
  const [progress, setProgress] = useState<ChatProgressStep[]>([]);
  const [dialog, setDialog] = useState<ChatDialogState>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [isDialogBusy, setIsDialogBusy] = useState(false);
  const aborter = useRef<AbortController | null>(null);
  const activeRunId = useRef<string | null>(null);
  const selectionRevision = useRef(0);

  const refreshSessions = useCallback(async () => {
    const loaded = await chatApi.list(client);
    setSessions(loaded.sessions);
    return loaded.sessions;
  }, [client]);

  useEffect(() => {
    void refreshSessions().catch(() => undefined);
    void chatApi.suggestions()
      .then(({ questions }) => {
        if (questions.length) setExamples(questions);
      })
      .catch(() => undefined);
    return () => aborter.current?.abort();
  }, [refreshSessions]);

  const selectSession = async (sessionId: string) => {
    if (isRunning) return;
    const revision = ++selectionRevision.current;
    setRequestError('');
    try {
      const selected = await chatApi.get(sessionId, client);
      if (revision === selectionRevision.current) setActive(selected);
    } catch (selectionError: unknown) {
      if (revision === selectionRevision.current) {
        setRequestError(errorMessage(selectionError, '대화를 불러오지 못했습니다.'));
      }
    }
  };

  const refreshSuggestions = async () => {
    if (isRefreshingSuggestions) return;
    setIsRefreshingSuggestions(true);
    try {
      const { questions } = await chatApi.refreshSuggestions();
      if (questions.length) setExamples(questions);
    } catch (suggestionError: unknown) {
      setRequestError(errorMessage(suggestionError, '추천 질문을 새로고침하지 못했습니다.'));
    } finally {
      setIsRefreshingSuggestions(false);
    }
  };

  const newSession = () => {
    if (isRunning) return;
    selectionRevision.current += 1;
    setActive(null);
    setDraft('');
    setAttachment(null);
    setRequestError('');
    setProgress([]);
  };

  const closeDialog = () => {
    if (isDialogBusy) return;
    setDialog(null);
    setDialogError(null);
  };

  const renameSession = async (nextTitle: string) => {
    if (!dialog || dialog.type !== 'rename') return;
    const { session } = dialog;
    const title = nextTitle.trim();
    if (!title) return;
    if (title === session.title) {
      setDialog(null);
      return;
    }
    setIsDialogBusy(true);
    setDialogError(null);
    try {
      const updated = await chatApi.rename(session.id, client, title);
      setSessions((items) => items.map((item) => item.id === updated.id ? updated : item));
      setActive((current) => current?.id === updated.id
        ? { ...current, title: updated.title, updated_at: updated.updated_at }
        : current);
      setDialog(null);
    } catch (renameError: unknown) {
      setDialogError(errorMessage(renameError, '대화 이름을 변경하지 못했습니다.'));
    } finally {
      setIsDialogBusy(false);
    }
  };

  const deleteSession = async () => {
    if (!dialog || dialog.type !== 'delete') return;
    const { session } = dialog;
    setIsDialogBusy(true);
    setDialogError(null);
    try {
      await chatApi.remove(session.id, client);
      setSessions((items) => items.filter((item) => item.id !== session.id));
      if (active?.id === session.id) newSession();
      setDialog(null);
    } catch (deleteError: unknown) {
      setDialogError(errorMessage(deleteError, '대화를 삭제하지 못했습니다.'));
    } finally {
      setIsDialogBusy(false);
    }
  };

  const streamAnswer = async (message: ChatMessage) => {
    const chunkSize = 12;
    for (let length = chunkSize; length < message.content.length; length += chunkSize) {
      if (aborter.current?.signal.aborted) return;
      const partial = { ...message, content: message.content.slice(0, length) };
      setActive((current) => current ? replaceMessage(current, message.id, partial) : current);
      await new Promise<void>((resolve) => window.setTimeout(resolve, 14));
    }
    setActive((current) => current ? replaceMessage(current, message.id, message) : current);
  };

  const ask = async (overrideValue?: string) => {
    const content = (overrideValue ?? draft).trim();
    if (!content || isRunning) return;
    setDraft('');
    setRequestError('');
    setIsRunning(true);
    setProgress([{ id: 'analysis', label: '질문을 분석하고 있습니다', state: 'active' }]);
    const controller = new AbortController();
    aborter.current = controller;

    try {
      let session: ChatSession;
      if (active) {
        session = active;
      } else {
        const created = await chatApi.create(client, controller.signal);
        session = { ...created, messages: [] };
        setActive(session);
      }

      const uploadedAttachment = attachment
        ? await chatApi.upload(session.id, client, attachment, controller.signal)
        : null;
      if (uploadedAttachment) setAttachment(null);

      const localUser: ChatMessage = {
        id: `local-${createUuid()}`,
        role: 'user',
        content,
        status: 'completed',
        run_id: null,
        visualization: null,
        attachments: uploadedAttachment ? [uploadedAttachment] : [],
        created_at: new Date().toISOString(),
      };
      setActive((current) => current
        ? { ...current, messages: [...(current.messages ?? []), localUser] }
        : { ...session, messages: [localUser] });

      const started = await chatApi.send(
        session.id,
        client,
        content,
        uploadedAttachment?.id,
        controller.signal,
      );
      setActive((current) => current && ({
        ...current,
        messages: [
          ...(current.messages ?? []).filter((message) => message.id !== localUser.id),
          { ...localUser, id: `user-${started.run_id}` },
          started.assistant_message,
        ],
      }));

      if (!started.run_id) {
        setProgress([{ id: 'answer', label: '답변을 작성하고 있습니다', state: 'active' }]);
        await refreshSessions();
        const completed = await chatApi.get(session.id, client, controller.signal);
        const answer = [...(completed.messages ?? [])].reverse().find((message) => message.role === 'assistant');
        setActive(answer
          ? { ...completed, messages: completed.messages?.map((message) =>
              message.id === answer.id ? { ...answer, content: '' } : message) }
          : completed);
        if (answer) await streamAnswer(answer);
        return;
      }

      activeRunId.current = started.run_id;
      const run = await pipelineApi.streamRun(
        started.run_id,
        (event) => {
          const updates = progressForEvent(event);
          if (updates.length) setProgress(updates);
        },
        controller.signal,
      );
      const synced = await chatApi.sync(run.id, client, controller.signal);
      if (synced.message) {
        const answer = synced.message;
        setActive((current) => current
          ? replaceMessage(current, answer.id, { ...answer, content: '' })
          : current);
        await streamAnswer(answer);
      }
      await refreshSessions();
    } catch (askError: unknown) {
      if (!isAbortError(askError)) {
        const message = errorMessage(askError, '질문 처리에 실패했습니다.');
        setRequestError(message);
        setActive((current) => current && ({
          ...current,
          messages: [...(current.messages ?? []), {
            id: `error-${createUuid()}`,
            role: 'assistant',
            content: message,
            status: 'failed',
            run_id: null,
            visualization: null,
            attachments: [],
            created_at: new Date().toISOString(),
          }],
        }));
      }
    } finally {
      aborter.current = null;
      activeRunId.current = null;
      setIsRunning(false);
      setProgress([]);
    }
  };

  const stop = () => {
    const runId = activeRunId.current;
    aborter.current?.abort();
    if (!runId) return;
    void pipelineApi.cancelRun(runId)
      .then(async () => {
        const synced = await chatApi.sync(runId, client);
        if (synced.message) {
          setActive((current) => current && synced.message
            ? replaceMessage(current, synced.message.id, synced.message)
            : current);
        }
        await refreshSessions();
      })
      .catch((stopError: unknown) => {
        setRequestError(errorMessage(stopError, '실행 중지에 실패했습니다.'));
      });
  };

  return {
    sessions,
    examples,
    isRefreshingSuggestions,
    active,
    messages: active?.messages ?? [],
    draft,
    attachment,
    isRunning,
    requestError,
    progress,
    dialog,
    dialogError,
    isDialogBusy,
    setDraft,
    setAttachment,
    selectSession,
    refreshSuggestions,
    newSession,
    ask,
    stop,
    requestRename: (session: ChatSession) => {
      setDialogError(null);
      setDialog({ type: 'rename', session });
    },
    requestDelete: (session: ChatSession) => {
      setDialogError(null);
      setDialog({ type: 'delete', session });
    },
    closeDialog,
    renameSession,
    deleteSession,
  };
}
