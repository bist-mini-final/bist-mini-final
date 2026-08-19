import { fireEvent, render, screen } from '@testing-library/react';
import { FileSpreadsheet } from 'lucide-react';
import { describe, expect, it, vi } from 'vitest';
import type { PipelineRunState } from '../../pipelineTypes';
import { PipelineTrackerView } from '../PipelineTrackerView';

function pipeline(status: PipelineRunState['status']): PipelineRunState {
  return {
    pipelineId: 'run-test',
    fileName: 'sample.xlsx',
    model: 'text-embedding-3-large',
    batchSize: 128,
    status,
    currentStageIndex: 0,
    progressPercent: 25,
    elapsedSeconds: 3,
    isLiveUpload: true,
    modules: [{
      id: 'selector',
      name: '처리 파일 선택',
      moduleType: 'processed_file_selector',
      category: 'Source',
      icon: FileSpreadsheet,
      status: status === 'paused' ? 'waiting' : 'running',
      sublogs: [],
    }],
  };
}

describe('PipelineTrackerView', () => {
  it('stops a running ingestion from the header', () => {
    const onCancel = vi.fn();
    render(
      <PipelineTrackerView
        pipeline={pipeline('running')}
        onBack={vi.fn()}
        onCancel={onCancel}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '작업 중단' }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('deletes a running ingestion from the header', () => {
    const onDelete = vi.fn();
    render(
      <PipelineTrackerView
        pipeline={pipeline('running')}
        onBack={vi.fn()}
        onDelete={onDelete}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '작업 삭제' }));

    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it('shows completed and total batch counts for the active module', () => {
    const running = pipeline('running');
    running.modules[0].batchProgress = {
      completed: 7,
      total: 12,
      completedItems: 7000,
      totalItems: 12000,
    };
    render(<PipelineTrackerView pipeline={running} onBack={vi.fn()} />);

    expect(screen.getByText('7/12 배치 완료')).toBeInTheDocument();
    expect(screen.getByText('문서 7,000/12,000개')).toBeInTheDocument();
  });

  it('shows a resumable paused state without a stop button', () => {
    render(
      <PipelineTrackerView
        pipeline={pipeline('paused')}
        onBack={vi.fn()}
        onResume={vi.fn()}
      />
    );

    expect(screen.getByText('사용자 중단')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '중단 지점부터 다시 실행' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '작업 중단' })).not.toBeInTheDocument();
  });
});
