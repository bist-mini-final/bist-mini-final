import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SettingsView } from '../SettingsView';
import { dataSourceApi } from '../../data-sources/services/dataSourceApi';

vi.mock('../../data-sources/services/dataSourceApi', () => ({
  dataSourceApi: {
    getDbStatus: vi.fn(),
  },
}));

describe('SettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders system settings and connected status banner', async () => {
    vi.mocked(dataSourceApi.getDbStatus).mockResolvedValue({
      connected: true,
      host: '192.168.5.4',
      port: 5432,
      database: 'rag_flow',
      postgres_version: '16.15',
      pgvector_version: '0.8.6',
      total_indexes: 2,
      total_chunks: 1024,
    });

    render(<SettingsView />);

    expect(screen.getByText('시스템 환경 & 인프라 설정')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('PostgreSQL pgvector 정상 연결됨')).toBeInTheDocument();
    });

    expect(screen.getByText('192.168.5.4:5432')).toBeInTheDocument();
    expect(
      screen.getByText('postgresql://<user>:<password>@192.168.5.4:5432/rag_flow')
    ).toBeInTheDocument();
    expect(screen.getByText('rag_flow')).toBeInTheDocument();
    expect(screen.getByText('2개')).toBeInTheDocument();
    expect(screen.getByText('1,024청크')).toBeInTheDocument();
    expect(screen.getByText('0.95 (보수적 임계값)')).toBeInTheDocument();
  });

  it('renders disconnected banner when pgvector DB is down', async () => {
    vi.mocked(dataSourceApi.getDbStatus).mockRejectedValue(new Error('Connection refused'));

    render(<SettingsView />);

    await waitFor(() => {
      expect(
        screen.getByText('pgvector 데이터베이스에 연결할 수 없습니다')
      ).toBeInTheDocument();
    });
  });
});
