import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatComposer } from './ChatComposer';
import { ChatMessages } from './ChatMessages';
import { ChatSessionSidebar } from './ChatSessionSidebar';
import type { ChatMessage, ChatSession } from './types';

const SESSION: ChatSession = {
  id: 'session-1',
  title: 'IBM 재무 분석',
  created_at: '2026-08-30T00:00:00Z',
  updated_at: '2026-08-30T01:00:00Z',
  messages: [],
};

describe('ChatComposer', () => {
  it('submits Enter, preserves Shift+Enter, and exposes the stop action while running', () => {
    const onAsk = vi.fn();
    const { rerender } = render(
      <ChatComposer
        draft="IBM 매출"
        attachment={null}
        isRunning={false}
        onDraftChange={vi.fn()}
        onAttachmentChange={vi.fn()}
        onAsk={onAsk}
        onStop={vi.fn()}
      />,
    );

    const textbox = screen.getByRole('textbox');
    fireEvent.keyDown(textbox, { key: 'Enter', shiftKey: true });
    expect(onAsk).not.toHaveBeenCalled();
    fireEvent.keyDown(textbox, { key: 'Enter' });
    expect(onAsk).toHaveBeenCalledOnce();

    const onStop = vi.fn();
    rerender(
      <ChatComposer
        draft=""
        attachment={null}
        isRunning
        onDraftChange={vi.fn()}
        onAttachmentChange={vi.fn()}
        onAsk={onAsk}
        onStop={onStop}
      />,
    );
    expect(screen.getByRole('textbox')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '중지' }));
    expect(onStop).toHaveBeenCalledOnce();
  });
});

describe('ChatMessages', () => {
  it('announces live progress and disables recommendations during a run', () => {
    const processing: ChatMessage = {
      id: 'assistant-1',
      role: 'assistant',
      content: '',
      status: 'processing',
      run_id: 'run-1',
      visualization: null,
      evidence: [],
      attachments: [],
      created_at: '2026-08-30T00:00:00Z',
      completed_at: null,
    };

    const { rerender } = render(
      <ChatMessages
        messages={[]}
        progress={[]}
        pendingTurn={null}
        examples={['추천 질문']}
        isRunning
        isRefreshingSuggestions={false}
        requestError=""
        onAskExample={vi.fn()}
        onRefreshSuggestions={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: '추천 질문' })).toBeDisabled();

    rerender(
      <ChatMessages
        messages={[processing]}
        progress={[{ id: 'search', label: '관련 재무 문서를 검색하고 있습니다', state: 'active' }]}
        pendingTurn={null}
        examples={[]}
        isRunning
        isRefreshingSuggestions={false}
        requestError=""
        onAskExample={vi.fn()}
        onRefreshSuggestions={vi.fn()}
      />,
    );
    expect(screen.getByText('관련 재무 문서를 검색하고 있습니다')).toBeInTheDocument();
    expect(screen.getByText('관련 재무 문서를 검색하고 있습니다').closest('.chatbot-messages'))
      .toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('관련 재무 문서를 검색하고 있습니다')
      .closest('.chatbot-message')?.querySelector('time'))
      .toHaveAttribute('datetime', '2026-08-30T00:00:00Z');
  });

  it('shows the submitted question and delivery state before the backend acknowledges it', () => {
    render(
      <ChatMessages
        messages={[]}
        progress={[{ id: 'submitting', label: '질문과 첨부 파일을 전달하고 있습니다', state: 'active' }]}
        pendingTurn={{
          content: '첨부 파일과 Nexora를 비교해줘',
          attachmentName: 'comparison.xlsx',
          createdAt: '2026-08-30T00:00:00Z',
        }}
        examples={['추천 질문']}
        isRunning
        isRefreshingSuggestions={false}
        requestError=""
        onAskExample={vi.fn()}
        onRefreshSuggestions={vi.fn()}
      />,
    );

    expect(screen.getByText('첨부 파일과 Nexora를 비교해줘')).toBeInTheDocument();
    expect(screen.getByText('comparison.xlsx')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('질문과 첨부 파일을 전달하고 있습니다');
    expect(screen.queryByText('새 재무 질문을 시작하세요')).not.toBeInTheDocument();
  });

  it('uses the assistant completion timestamp after the response arrives', () => {
    const completed: ChatMessage = {
      id: 'assistant-completed',
      role: 'assistant',
      content: '완료된 답변',
      status: 'completed',
      run_id: 'run-completed',
      visualization: null,
      evidence: [],
      attachments: [],
      created_at: '2026-08-30T00:00:00Z',
      completed_at: '2026-08-30T00:02:00Z',
    };

    const { container } = render(
      <ChatMessages
        messages={[completed]}
        progress={[]}
        pendingTurn={null}
        examples={[]}
        isRunning={false}
        isRefreshingSuggestions={false}
        requestError=""
        onAskExample={vi.fn()}
        onRefreshSuggestions={vi.fn()}
      />,
    );

    expect(container.querySelector('.chatbot-message time'))
      .toHaveAttribute('datetime', '2026-08-30T00:02:00Z');
  });
});

describe('ChatSessionSidebar', () => {
  it('renders reusable session controls for the application sidebar', () => {
    const onSelectSession = vi.fn();

    render(
      <ChatSessionSidebar
        sessions={[SESSION]}
        activeSessionId={SESSION.id}
        disabled={false}
        onSelectSession={onSelectSession}
        onRenameSession={vi.fn()}
        onDeleteSession={vi.fn()}
      />,
    );

    expect(screen.getByText('대화 이력')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'IBM 재무 분석 제목 편집' }))
      .toHaveClass('chatbot-session__action', 'is-edit');
    expect(screen.getByRole('button', { name: 'IBM 재무 분석 삭제' }))
      .toHaveClass('chatbot-session__action', 'is-delete');
    fireEvent.click(screen.getByRole('button', { name: 'IBM 재무 분석' }));
    expect(onSelectSession).toHaveBeenCalledWith(SESSION.id);
  });
});
