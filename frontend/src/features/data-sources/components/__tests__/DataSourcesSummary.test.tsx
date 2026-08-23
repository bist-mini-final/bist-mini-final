import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DataSourcesSummary } from '../DataSourcesSummary';
import type { DbStatusInfo, VectorIndexInfo } from '../../types';

describe('DataSourcesSummary', () => {
  it('renders zero counts properly when no indexes exist', () => {
    const dbStatus: DbStatusInfo = {
      connected: true,
      host: 'localhost',
      port: 5432,
      database: 'rag_flow',
      postgres_version: '16.15',
      pgvector_version: '0.8.6',
      total_indexes: 0,
      total_chunks: 0,
    };

    render(<DataSourcesSummary indexes={[]} dbStatus={dbStatus} />);

    expect(screen.getByText('pgvector 컬렉션')).toBeInTheDocument();
    expect(screen.getAllByText('0')).toHaveLength(2);
    expect(screen.getByText('총 벡터 임베딩 청크')).toBeInTheDocument();
    expect(screen.getByText('PostgreSQL 16')).toBeInTheDocument();
    expect(screen.getByText('인덱스 미등록')).toBeInTheDocument();
    expect(screen.getByText('인덱스 모델·차원 자동 동기화')).toBeInTheDocument();
  });

  it('renders correct collection and chunk aggregations', () => {
    const indexes: VectorIndexInfo[] = [
      {
        index_id: 'col-1',
        file_name: 'workbook1.xlsx',
        workbook_hash: 'hash1',
        model: 'text-embedding-3-large',
        dimension: 3072,
        document_count: 150,
        created_at: new Date().toISOString(),
      },
      {
        index_id: 'col-2',
        file_name: 'workbook2.xlsx',
        workbook_hash: 'hash2',
        model: 'text-embedding-3-large',
        dimension: 3072,
        document_count: 350,
        created_at: new Date().toISOString(),
      },
    ];

    render(<DataSourcesSummary indexes={indexes} dbStatus={null} />);

    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('500')).toBeInTheDocument();
    expect(screen.getByText('연결 대기 중')).toBeInTheDocument();
    expect(screen.getByText('text-embedding-3-large')).toBeInTheDocument();
    expect(screen.getByText('3072차원 · 질의 모델 자동 동기화')).toBeInTheDocument();
  });
});
