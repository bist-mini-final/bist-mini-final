import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { FileSpreadsheet } from 'lucide-react';
import { VectorIndexList } from '../VectorIndexList';
import type { VectorIndexInfo } from '../../types';
import type { PipelineRunState } from '../../pipelineTypes';

const dataSourceApiMocks = vi.hoisted(() => ({
  updateIndexCompany: vi.fn(),
}));

vi.mock('../../services/dataSourceApi', () => ({
  dataSourceApi: dataSourceApiMocks,
}));

describe('VectorIndexList', () => {
  beforeEach(() => {
    dataSourceApiMocks.updateIndexCompany.mockReset();
  });

  it('renders empty state when no collections exist', () => {
    const handleCreate = vi.fn();
    render(
      <VectorIndexList
        indexes={[]}
        onDetailClick={vi.fn()}
        onSearchClick={vi.fn()}
        onDeleteClick={vi.fn()}
        onCreateClick={handleCreate}
      />
    );

    expect(
      screen.getByText('pgvector 데이터베이스에 등록된 컬렉션이 없습니다')
    ).toBeInTheDocument();

    const startBtn = screen.getByRole('button', { name: /새 엑셀 인덱싱 시작/i });
    fireEvent.click(startBtn);
    expect(handleCreate).toHaveBeenCalledTimes(1);
  });

  it('renders table rows and triggers actions on click', () => {
    const mockIndexes: VectorIndexInfo[] = [
      {
        index_id: 'col-uuid-1234567890',
        file_name: 'test_company.xlsx',
        workbook_hash: 'hash-test',
        model: 'text-embedding-3-large',
        dimension: 3072,
        document_count: 128,
        created_at: '2026-08-18T10:00:00Z',
      },
    ];

    const handleDetail = vi.fn();
    const handleSearch = vi.fn();
    const handleDelete = vi.fn();

    render(
      <VectorIndexList
        indexes={mockIndexes}
        onDetailClick={handleDetail}
        onSearchClick={handleSearch}
        onDeleteClick={handleDelete}
        onCreateClick={vi.fn()}
      />
    );

    expect(screen.getByText('test_company.xlsx')).toBeInTheDocument();
    expect(screen.getByText('3072D')).toBeInTheDocument();
    expect(screen.getByText('128개')).toBeInTheDocument();

    const searchBtn = screen.getByRole('button', { name: /검색 테스트/i });
    fireEvent.click(searchBtn);
    expect(handleSearch).toHaveBeenCalledWith(mockIndexes[0]);

    const detailBtn = screen.getByRole('button', { name: /상세/i });
    fireEvent.click(detailBtn);
    expect(handleDetail).toHaveBeenCalledWith('col-uuid-1234567890');

    const deleteBtn = screen.getByRole('button', { name: /삭제/i });
    fireEvent.click(deleteBtn);
    expect(handleDelete).toHaveBeenCalledWith('col-uuid-1234567890');
  });

  it('does not render a DB collection twice while its owning pipeline is active', () => {
    const index: VectorIndexInfo = {
      index_id: 'target-index',
      file_name: 'sample.xlsx',
      workbook_hash: 'hash-test',
      model: 'text-embedding-3-large',
      dimension: 3072,
      document_count: 1000,
      created_at: '2026-08-18T10:00:00Z',
    };
    const pipeline: PipelineRunState = {
      pipelineId: 'run-active',
      targetIndexId: 'target-index',
      fileName: 'sample.xlsx',
      model: 'text-embedding-3-large',
      batchSize: 1000,
      status: 'running',
      currentStageIndex: 0,
      progressPercent: 80,
      elapsedSeconds: 10,
      modules: [{
        id: 'writer',
        name: 'pgvector 적재',
        moduleType: 'pgvector_index_writer',
        category: 'Storage',
        icon: FileSpreadsheet,
        status: 'running',
        sublogs: [],
      }],
    };

    render(
      <VectorIndexList
        indexes={[index]}
        activeRunningPipeline={pipeline}
        onDetailClick={vi.fn()}
        onSearchClick={vi.fn()}
        onDeleteClick={vi.fn()}
        onCreateClick={vi.fn()}
      />
    );

    expect(screen.getAllByText('sample.xlsx')).toHaveLength(1);
    expect(screen.queryByText('1,000개')).not.toBeInTheDocument();
  });

  it('shows the persisted collection after its pipeline completes', () => {
    const index: VectorIndexInfo = {
      index_id: 'target-index',
      file_name: 'completed.xlsx',
      workbook_hash: 'hash-test',
      model: 'text-embedding-3-small',
      dimension: 1536,
      document_count: 42,
      created_at: '2026-08-18T10:00:00Z',
    };
    const completed: PipelineRunState = {
      pipelineId: 'run-completed',
      targetIndexId: 'target-index',
      fileName: 'completed.xlsx',
      model: 'text-embedding-3-small',
      batchSize: 128,
      status: 'completed',
      currentStageIndex: 0,
      progressPercent: 100,
      elapsedSeconds: 3,
      modules: [],
    };

    render(
      <VectorIndexList
        indexes={[index]}
        activeRunningPipeline={completed}
        onDetailClick={vi.fn()}
        onSearchClick={vi.fn()}
        onDeleteClick={vi.fn()}
        onCreateClick={vi.fn()}
      />
    );

    expect(screen.getByText('completed.xlsx')).toBeInTheDocument();
    expect(screen.getByText('42개')).toBeInTheDocument();
  });

  it('edits a company name and refreshes the persisted collection list', async () => {
    const index: VectorIndexInfo = {
      index_id: 'company-index',
      file_name: 'company.xlsx',
      company_name: 'Old Company',
      workbook_hash: 'hash-company',
      model: 'text-embedding-3-large',
      dimension: 3072,
      document_count: 25,
      created_at: '2026-08-18T10:00:00Z',
    };
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    dataSourceApiMocks.updateIndexCompany.mockResolvedValue({
      status: 'success',
      index_id: index.index_id,
      company_name: 'New Company',
    });

    render(
      <VectorIndexList
        indexes={[index]}
        onRefresh={onRefresh}
        onDetailClick={vi.fn()}
        onSearchClick={vi.fn()}
        onDeleteClick={vi.fn()}
        onCreateClick={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Old Company 기업명 수정' }));
    fireEvent.change(screen.getByRole('textbox', { name: '기업명' }), {
      target: { value: ' New Company ' },
    });
    fireEvent.click(screen.getByRole('button', { name: '기업명 저장' }));

    await waitFor(() => {
      expect(dataSourceApiMocks.updateIndexCompany)
        .toHaveBeenCalledWith('company-index', 'New Company');
      expect(onRefresh).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByRole('textbox', { name: '기업명' })).not.toBeInTheDocument();
  });

  it('announces that a company name update is in progress and locks conflicting controls', async () => {
    const index: VectorIndexInfo = {
      index_id: 'pending-company-index',
      file_name: 'pending-company.xlsx',
      company_name: 'Old Company',
      workbook_hash: 'hash-pending-company',
      model: 'text-embedding-3-large',
      dimension: 3072,
      document_count: 25,
      created_at: '2026-08-18T10:00:00Z',
    };
    let resolveUpdate!: (value: {
      status: string;
      index_id: string;
      company_name: string;
    }) => void;
    dataSourceApiMocks.updateIndexCompany.mockReturnValue(new Promise((resolve) => {
      resolveUpdate = resolve;
    }));

    render(
      <VectorIndexList
        indexes={[index]}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onDetailClick={vi.fn()}
        onSearchClick={vi.fn()}
        onDeleteClick={vi.fn()}
        onCreateClick={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Old Company 기업명 수정' }));
    fireEvent.change(screen.getByRole('textbox', { name: '기업명' }), {
      target: { value: 'New Company' },
    });
    fireEvent.click(screen.getByRole('button', { name: '기업명 저장' }));

    expect(await screen.findByRole('status')).toHaveTextContent('기업명 변경 중...');
    expect(screen.getByRole('textbox', { name: '기업명' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '기업명 저장' })).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('button', { name: /검색 테스트/i })).toBeDisabled();

    resolveUpdate({
      status: 'success',
      index_id: index.index_id,
      company_name: 'New Company',
    });
    await waitFor(() => {
      expect(screen.queryByText('기업명 변경 중...')).not.toBeInTheDocument();
    });
  });

  it('shows an in-row deletion state while a data collection is being removed', () => {
    const index: VectorIndexInfo = {
      index_id: 'deleting-index',
      file_name: 'deleting-company.xlsx',
      company_name: 'Deleting Company',
      workbook_hash: 'hash-deleting-company',
      model: 'text-embedding-3-large',
      dimension: 3072,
      document_count: 25,
      created_at: '2026-08-18T10:00:00Z',
    };

    render(
      <VectorIndexList
        indexes={[index]}
        deletingIndexId={index.index_id}
        onDetailClick={vi.fn()}
        onSearchClick={vi.fn()}
        onDeleteClick={vi.fn()}
        onCreateClick={vi.fn()}
      />
    );

    expect(screen.getByRole('status')).toHaveTextContent('데이터 삭제 중...');
    expect(screen.getByText('deleting-company.xlsx').closest('tr')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByRole('button', { name: '인덱스 삭제' })).not.toBeInTheDocument();
  });

  it('keeps the editor open and shows an inline error for an empty company name', async () => {
    const index: VectorIndexInfo = {
      index_id: 'empty-company-index',
      file_name: 'company.xlsx',
      company_name: 'Old Company',
      workbook_hash: 'hash-company',
      model: 'text-embedding-3-small',
      dimension: 1536,
      document_count: 10,
      created_at: '2026-08-18T10:00:00Z',
    };

    render(
      <VectorIndexList
        indexes={[index]}
        onDetailClick={vi.fn()}
        onSearchClick={vi.fn()}
        onDeleteClick={vi.fn()}
        onCreateClick={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Old Company 기업명 수정' }));
    fireEvent.change(screen.getByRole('textbox', { name: '기업명' }), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: '기업명 저장' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('기업명을 입력해 주세요.');
    expect(screen.getByRole('textbox', { name: '기업명' })).toBeInTheDocument();
    expect(dataSourceApiMocks.updateIndexCompany).not.toHaveBeenCalled();
  });
});
