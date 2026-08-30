import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Header } from './Header';

describe('Playground Header', () => {
  it('opens the workflow creator beside the selector and omits benchmark comparison', () => {
    const onOpenWorkflowCreator = vi.fn();
    render(<Header
      activeStep={-1}
      totalSteps={0}
      hasGraphCycle={false}
      isRunning={false}
      hasPipeline={false}
      isPaletteOpen={false}
      onTogglePalette={vi.fn()}
      onReset={vi.fn()}
      onToggleRun={vi.fn()}
      saveStatus="saved"
      onSave={vi.fn()}
      isClearingCache={false}
      onClearCache={vi.fn()}
      workflows={[{
        id: 'rag_query',
        name: 'RAG Query',
        kind: 'standard',
        editable: false,
        template: true,
        nodeCount: 10,
        edgeCount: 10,
        moduleTypes: [],
      }]}
      activeWorkflowId="rag_query"
      onSelectWorkflow={vi.fn()}
      onOpenWorkflowCreator={onOpenWorkflowCreator}
    />);

    expect(screen.getByRole('option', { name: 'RAG Query · 읽기 전용' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '새 워크플로' }));
    expect(onOpenWorkflowCreator).toHaveBeenCalledOnce();
    expect(screen.queryByRole('button', { name: '성능 비교' })).not.toBeInTheDocument();
  });
});
