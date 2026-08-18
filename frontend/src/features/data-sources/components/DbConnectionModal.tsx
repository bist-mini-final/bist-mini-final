import { useState } from 'react';
import {
  CheckCircle2,
  Database,
  HardDrive,
  Layers,
  Loader2,
  Server,
  ShieldCheck,
  X,
  XCircle,
} from 'lucide-react';
import { dataSourceApi } from '../services/dataSourceApi';
import type { DbStatusInfo } from '../types';

interface DbModalProps {
  status: DbStatusInfo | null;
  onClose: () => void;
  onRefresh: () => void;
}

export function DbConnectionModal({ status, onClose, onRefresh }: DbModalProps) {
  const [dbUrl, setDbUrl] = useState(
    `postgresql://postgres:postgres@${status?.host || 'localhost'}:${status?.port || 5432}/${
      status?.database || 'rag_flow'
    }`
  );
  const [testResult, setTestResult] = useState<DbStatusInfo | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  const handleTest = async () => {
    setIsTesting(true);
    try {
      const res = await dataSourceApi.testDbConnect(dbUrl);
      setTestResult(res);
      if (res.connected) {
        onRefresh();
      }
    } catch (err: any) {
      setTestResult({
        connected: false,
        host: 'unknown',
        port: 5432,
        database: 'rag_flow',
        total_indexes: 0,
        total_chunks: 0,
        error: err.message || '접속 테스트 실패',
      });
    } finally {
      setIsTesting(false);
    }
  };

  const isConnected = testResult ? testResult.connected : status?.connected;

  return (
    <div className="ds-modal-backdrop" onClick={onClose}>
      <div
        className="ds-modal ds-modal--medium"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="db-modal-title"
      >
        <header className="ds-modal__header">
          <div className="ds-modal__title-wrap">
            <span
              className={`ds-modal__icon ${
                isConnected ? 'ds-modal__icon--green' : 'ds-modal__icon--blue'
              }`}
            >
              <Database size={19} />
            </span>
            <div>
              <h3 id="db-modal-title">Docker pgvector 데이터베이스 설정</h3>
              <small>PostgreSQL 16 + pgvector 확장 컨테이너 접속 관리</small>
            </div>
          </div>
          <button className="ds-modal__close" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </button>
        </header>

        <div className="ds-modal__body">
          {/* Status banner */}
          <div
            className={`ds-db-banner ${
              isConnected ? 'ds-db-banner--connected' : 'ds-db-banner--disconnected'
            }`}
          >
            <div className="ds-db-banner__icon">
              {isConnected ? (
                <CheckCircle2 size={22} className="ds-icon-success" />
              ) : (
                <XCircle size={22} className="ds-icon-danger" />
              )}
            </div>
            <div>
              <strong>
                {isConnected
                  ? 'pgvector Docker 컨테이너 정상 연결됨'
                  : 'pgvector 데이터베이스 연결 끊김'}
              </strong>
              <p>
                {isConnected
                  ? `PostgreSQL ${status?.postgres_version || '16'} (pgvector 확장 v${
                      status?.pgvector_version || '0.8.6'
                    })`
                  : status?.error || 'docker compose up -d 명령어로 컨테이너를 실행하세요.'}
              </p>
            </div>
          </div>

          {/* Database stats grid */}
          {status && status.connected && (
            <div className="ds-db-stats-grid">
              <div className="ds-db-stat">
                <Server size={15} />
                <div>
                  <small>호스트 및 포트</small>
                  <strong>{status.host}:{status.port}</strong>
                </div>
              </div>
              <div className="ds-db-stat">
                <HardDrive size={15} />
                <div>
                  <small>데이터베이스</small>
                  <strong>{status.database}</strong>
                </div>
              </div>
              <div className="ds-db-stat">
                <ShieldCheck size={15} />
                <div>
                  <small>pgvector 버전</small>
                  <strong>v{status.pgvector_version}</strong>
                </div>
              </div>
              <div className="ds-db-stat">
                <Layers size={15} />
                <div>
                  <small>적재된 벡터 청크</small>
                  <strong>{status.total_chunks.toLocaleString()}개</strong>
                </div>
              </div>
            </div>
          )}

          {/* Connection URL form */}
          <div className="ds-form-group" style={{ marginTop: '1rem' }}>
            <label className="ds-form-label">
              <span>PostgreSQL 접속 URL</span>
            </label>
            <input
              type="text"
              className="ds-search-input ds-font-mono"
              style={{ fontSize: '0.74rem' }}
              value={dbUrl}
              onChange={(e) => setDbUrl(e.target.value)}
            />
            <small style={{ color: '#8c9891', fontSize: '0.66rem', marginTop: '0.3rem' }}>
              기본값: postgresql://postgres:postgres@localhost:5432/rag_flow (Docker 컨테이너 포트 5432)
            </small>
          </div>
        </div>

        <footer className="ds-modal__footer">
          <button
            type="button"
            className="secondary-button"
            onClick={handleTest}
            disabled={isTesting}
          >
            {isTesting ? <Loader2 size={15} className="ds-spin" /> : '연결 테스트'}
          </button>
          <button type="button" className="primary-button" onClick={onClose}>
            확인
          </button>
        </footer>
      </div>
    </div>
  );
}
