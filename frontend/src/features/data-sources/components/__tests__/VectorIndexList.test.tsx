import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { VectorIndexList } from '../VectorIndexList';
import type { VectorIndexInfo } from '../../types';

describe('VectorIndexList', () => {
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
});
