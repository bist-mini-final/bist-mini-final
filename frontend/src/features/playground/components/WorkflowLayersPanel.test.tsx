import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkflowLayersPanel } from './WorkflowLayersPanel';

describe('WorkflowLayersPanel template gallery', () => {
  it('previews canonical templates and selects one for creation', () => {
    const onCreateFromTemplate = vi.fn();
    render(<WorkflowLayersPanel
      nodes={[]}
      edges={[]}
      modules={[]}
      workflows={[
        {
          id: 'rag_query',
          name: 'RAG Query',
          nodeCount: 7,
          edgeCount: 8,
          moduleTypes: ['query_input', 'reader'],
        },
      ]}
      activeWorkflowId="rag_query"
      onSelectWorkflow={vi.fn()}
      onCreateWorkflow={vi.fn()}
      onDuplicateWorkflow={vi.fn()}
      onCreateFromTemplate={onCreateFromTemplate}
      onRenameWorkflow={vi.fn()}
      onDeleteWorkflow={vi.fn()}
      onSelectNode={vi.fn()}
      onDuplicateNode={vi.fn()}
      readOnly
    />);

    fireEvent.click(screen.getByTitle('템플릿 갤러리'));
    expect(screen.getByRole('dialog', { name: '워크플로 템플릿 갤러리' })).toBeInTheDocument();
    expect(screen.getByText('7 nodes · 8 connections')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '이 템플릿으로 생성' }));
    expect(onCreateFromTemplate).toHaveBeenCalledWith('rag_query');
  });
});
