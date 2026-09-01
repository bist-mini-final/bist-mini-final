import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatSession } from './types';

const chatApiMock = vi.hoisted(() => ({
  list: vi.fn(),
  suggestions: vi.fn(),
  refreshSuggestions: vi.fn(),
  create: vi.fn(),
  get: vi.fn(),
  rename: vi.fn(),
  remove: vi.fn(),
  upload: vi.fn(),
  send: vi.fn(),
  sync: vi.fn(),
}));

vi.mock('./chatApi', () => ({ chatApi: chatApiMock }));
vi.mock('../playground/services/api', () => ({
  pipelineApi: {
    streamRun: vi.fn(),
    cancelRun: vi.fn(),
  },
}));

import { progressForEvent, useChatController } from './useChatController';

function session(id: string): ChatSession {
  return {
    id,
    title: id,
    created_at: '2026-08-30T00:00:00Z',
    updated_at: '2026-08-30T00:00:00Z',
    messages: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

describe('progressForEvent', () => {
  it('maps running pipeline modules to user-facing progress', () => {
    expect(progressForEvent({
      event: 'node_started',
      data: { node_id: 'query_embedder', module_type: 'embedder', status: 'running' },
    })).toEqual([{
      id: 'query_embedder',
      label: '질문을 벡터로 변환하고 있습니다',
      state: 'active',
    }]);

    expect(progressForEvent({
      event: 'node_completed',
      data: { node_id: 'reader', module_type: 'llm', status: 'completed' },
    })).toEqual([]);
  });
});

describe('useChatController', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    chatApiMock.list.mockResolvedValue({ sessions: [] });
    chatApiMock.suggestions.mockResolvedValue({ questions: [] });
  });

  it('keeps the newest session selection when earlier requests finish late', async () => {
    const first = deferred<ChatSession>();
    const second = deferred<ChatSession>();
    chatApiMock.get.mockImplementation((id: string) => (
      id === 'first' ? first.promise : second.promise
    ));

    const { result } = renderHook(() => useChatController());
    await waitFor(() => expect(chatApiMock.list).toHaveBeenCalledOnce());

    let firstSelection!: Promise<void>;
    let secondSelection!: Promise<void>;
    act(() => {
      firstSelection = result.current.selectSession('first');
      secondSelection = result.current.selectSession('second');
    });

    await act(async () => {
      second.resolve(session('second'));
      await secondSelection;
    });
    expect(result.current.active?.id).toBe('second');

    await act(async () => {
      first.resolve(session('first'));
      await firstSelection;
    });
    expect(result.current.active?.id).toBe('second');
  });

  it('exposes the pending question before a new session is acknowledged', async () => {
    chatApiMock.create.mockReturnValue(new Promise(() => undefined));

    const { result } = renderHook(() => useChatController());
    await waitFor(() => expect(chatApiMock.list).toHaveBeenCalledOnce());

    act(() => {
      void result.current.ask('Nexora의 매출 추이를 알려줘');
    });

    expect(result.current.isRunning).toBe(true);
    expect(result.current.pendingTurn).toMatchObject({
      content: 'Nexora의 매출 추이를 알려줘',
      attachmentName: null,
    });
    expect(result.current.progress).toEqual([{
      id: 'submitting',
      label: '질문을 전달하고 있습니다',
      state: 'active',
    }]);
  });
});
