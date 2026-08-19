import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SettingsView } from '../SettingsView';
import { dataSourceApi } from '../../data-sources/services/dataSourceApi';

vi.mock('../../data-sources/services/dataSourceApi', () => ({
  dataSourceApi: {
    getDbStatus: vi.fn(),
  },
}));

describe('SettingsView', () => {
  const originalClipboard = navigator.clipboard;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: originalClipboard,
      writable: true,
      configurable: true,
    });
  });

  it('renders system settings and connected status banner', async () => {
    vi.mocked(dataSourceApi.getDbStatus).mockResolvedValue({
      connected: true,
      host: 'localhost',
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

    expect(screen.getByText('localhost:5432')).toBeInTheDocument();
    expect(screen.getByText('rag_flow')).toBeInTheDocument();
    expect(screen.getByText('2개')).toBeInTheDocument();
    expect(screen.getByText('1,024청크')).toBeInTheDocument();
    expect(screen.getByText('0.95 (보수적 임계값)')).toBeInTheDocument();
    expect(
      screen.getByText('postgresql://<user>:<password>@localhost:5432/rag_flow')
    ).toBeInTheDocument();
  });

  it('renders custom host, port, and database in dbUrl', async () => {
    vi.mocked(dataSourceApi.getDbStatus).mockResolvedValue({
      connected: true,
      host: '10.0.1.20',
      port: 5433,
      database: 'custom_warehouse',
      total_indexes: 5,
      total_chunks: 5000,
    });

    render(<SettingsView />);

    await waitFor(() => {
      expect(
        screen.getByText('postgresql://<user>:<password>@10.0.1.20:5433/custom_warehouse')
      ).toBeInTheDocument();
    });
  });

  it('copies dbUrl and dockerCmd to clipboard successfully', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      writable: true,
      configurable: true,
    });

    vi.mocked(dataSourceApi.getDbStatus).mockResolvedValue({
      connected: true,
      host: 'localhost',
      port: 5432,
      database: 'rag_flow',
      total_indexes: 1,
      total_chunks: 100,
    });

    render(<SettingsView />);

    await waitFor(() => {
      expect(screen.getByText('PostgreSQL pgvector 정상 연결됨')).toBeInTheDocument();
    });

    const copyUrlBtn = screen.getByRole('button', { name: /URL 복사/i });
    const copyCmdBtn = screen.getByRole('button', { name: /명령어 복사/i });

    fireEvent.click(copyUrlBtn);
    expect(writeTextMock).toHaveBeenCalledWith(
      'postgresql://<user>:<password>@localhost:5432/rag_flow'
    );
    await waitFor(() => {
      expect(screen.getByText('복사됨!')).toBeInTheDocument();
    });

    fireEvent.click(copyCmdBtn);
    expect(writeTextMock).toHaveBeenCalledWith(
      'docker compose -f docker-compose.db.yml up -d'
    );
    await waitFor(() => {
      expect(screen.getByText('복사됨!')).toBeInTheDocument();
    });
  });

  it('handles clipboard writeText rejection gracefully without showing copied state', async () => {
    const writeTextMock = vi.fn().mockRejectedValue(new Error('Permission denied'));
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      writable: true,
      configurable: true,
    });

    vi.mocked(dataSourceApi.getDbStatus).mockResolvedValue({
      connected: true,
      host: 'localhost',
      port: 5432,
      database: 'rag_flow',
      total_indexes: 1,
      total_chunks: 100,
    });

    render(<SettingsView />);

    await waitFor(() => {
      expect(screen.getByText('PostgreSQL pgvector 정상 연결됨')).toBeInTheDocument();
    });

    const copyUrlBtn = screen.getByRole('button', { name: /URL 복사/i });
    fireEvent.click(copyUrlBtn);

    expect(writeTextMock).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByText('복사 실패')).toBeInTheDocument();
    });
    expect(screen.queryByText('복사됨!')).not.toBeInTheDocument();
  });

  it('handles missing or unsupported navigator.clipboard gracefully with failure feedback', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      writable: true,
      configurable: true,
    });

    vi.mocked(dataSourceApi.getDbStatus).mockResolvedValue({
      connected: true,
      host: 'localhost',
      port: 5432,
      database: 'rag_flow',
      total_indexes: 1,
      total_chunks: 100,
    });

    render(<SettingsView />);

    await waitFor(() => {
      expect(screen.getByText('PostgreSQL pgvector 정상 연결됨')).toBeInTheDocument();
    });

    const copyUrlBtn = screen.getByRole('button', { name: /URL 복사/i });
    fireEvent.click(copyUrlBtn);

    await waitFor(() => {
      expect(screen.getByText('복사 실패')).toBeInTheDocument();
    });
    expect(screen.queryByText('복사됨!')).not.toBeInTheDocument();
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
