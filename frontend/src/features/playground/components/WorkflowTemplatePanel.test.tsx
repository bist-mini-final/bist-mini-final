import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkflowTemplatePanel } from './WorkflowTemplatePanel';

describe('WorkflowTemplatePanel', () => {
  it('shows backend-designated templates with their actual graph counts', () => {
    const onClose = vi.fn();
    const onCreateFromTemplate = vi.fn();
    render(<WorkflowTemplatePanel
      isOpen
      isLoading={false}
      workflows={[
        {
          id: 'rag_query',
          name: '하이브리드 재무 질의응답 RAG 파이프라인',
          kind: 'standard',
          editable: false,
          template: true,
          nodeCount: 10,
          edgeCount: 10,
          moduleTypes: ['query_input', 'reader'],
        },
        {
          id: 'user-workflow',
          name: '사용자 워크플로',
          kind: 'user',
          editable: true,
          template: false,
          nodeCount: 2,
          edgeCount: 1,
          moduleTypes: ['query_input', 'reader'],
        },
      ]}
      modules={[]}
      onClose={onClose}
      onCreateFromTemplate={onCreateFromTemplate}
    />);

    expect(screen.getByRole('dialog', { name: '새 워크플로 만들기' })).toBeInTheDocument();
    expect(screen.getByText('표준 파이프라인을 복사해 모듈과 연결을 자유롭게 수정할 수 있습니다.')).toBeInTheDocument();
    expect(screen.getByText('읽기 전용 원본은 그대로 유지됩니다.')).toBeInTheDocument();
    expect(screen.getByText('10 nodes · 10 connections')).toBeInTheDocument();
    expect(screen.queryByText('0 nodes · 0 connections')).not.toBeInTheDocument();
    expect(screen.queryByText('사용자 워크플로')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '편집 가능한 사본 만들기' }));
    expect(onCreateFromTemplate).toHaveBeenCalledWith('rag_query');
    expect(onClose).toHaveBeenCalledOnce();
  });
});
