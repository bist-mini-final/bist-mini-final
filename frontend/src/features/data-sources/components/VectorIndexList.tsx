import {
  Clock,
  Database,
  Eye,
  Layers,
  RefreshCw,
  Search,
  Server,
  Sparkles,
  Trash2,
} from 'lucide-react';
import type { DbStatusInfo, VectorIndexInfo } from '../types';

interface VectorIndexListProps {
  indexes: VectorIndexInfo[];
  dbStatus?: DbStatusInfo | null;
  isLoading?: boolean;
  onRefresh?: () => void;
  onDbModalClick?: () => void;
  onDetailClick: (indexId: string) => void;
  onSearchClick: (index: VectorIndexInfo) => void;
  onDeleteClick: (indexId: string) => void;
  onCreateClick: () => void;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function VectorIndexList({
  indexes,
  dbStatus,
  isLoading,
  onRefresh,
  onDbModalClick,
  onDetailClick,
  onSearchClick,
  onDeleteClick,
  onCreateClick,
}: VectorIndexListProps) {
  return (
    <div className="ds-panel">
      <div className="ds-panel__header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <h3>PostgreSQL pgvector 컬렉션 목록</h3>
            {dbStatus && (
              <button
                type="button"
                className={`ds-db-status-pill ${dbStatus.connected ? 'is-connected' : 'is-disconnected'}`}
                onClick={onDbModalClick}
                title="PostgreSQL pgvector 연결 정보 확인"
                style={{ padding: '0.2rem 0.6rem', fontSize: '0.78rem' }}
              >
                <span className="ds-db-status-pill__dot" />
                <Server size={11} />
                <span>
                  {dbStatus.connected
                    ? `localhost:${dbStatus.port} / ${dbStatus.database}`
                    : '연결 안 됨'}
                </span>
              </button>
            )}
          </div>
          <small>PostgreSQL 16 + pgvector에 적재된 LangChain 표준 벡터 컬렉션 (HNSW 코사인 유사도 인덱스)</small>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {onRefresh && (
            <button
              type="button"
              className="secondary-button"
              onClick={onRefresh}
              title="새로고침"
              disabled={isLoading}
            >
              <RefreshCw size={14} className={isLoading ? 'ds-spin' : ''} />
              <span>새로고침</span>
            </button>
          )}
          <button type="button" className="primary-button" onClick={onCreateClick}>
            <Sparkles size={15} /> 새 엑셀 인덱싱
          </button>
        </div>
      </div>

      {indexes.length === 0 ? (
        <div className="ds-empty-state">
          <Database size={44} />
          <h4>pgvector 데이터베이스에 등록된 컬렉션이 없습니다</h4>
          <p>엑셀 파일을 업로드하면 Luna VLM 표 구조 분석과 4필드 직렬화를 거쳐 pgvector로 벡터 인덱스가 즉시 생성됩니다.</p>
          <button type="button" className="primary-button" onClick={onCreateClick}>
            <Sparkles size={15} /> 새 엑셀 인덱싱 시작
          </button>
        </div>
      ) : (
        <div className="ds-table-container">
          <table className="ds-table">
            <thead>
              <tr>
                <th>컬렉션 ID</th>
                <th>대상 데이터셋</th>
                <th>임베딩 모델</th>
                <th>차원</th>
                <th>저장된 청크 수</th>
                <th>스토리지</th>
                <th>생성일시</th>
                <th className="ds-text-right">작업</th>
              </tr>
            </thead>
            <tbody>
              {indexes.map((idx) => (
                <tr key={idx.index_id}>
                  <td className="ds-font-mono ds-id-cell">
                    <span title={idx.index_id}>{idx.index_id.slice(0, 12)}...</span>
                  </td>
                  <td>
                    <strong>{idx.file_name || 'Dataset'}</strong>
                  </td>
                  <td>
                    <span className="ds-badge ds-badge--blue">{idx.model}</span>
                  </td>
                  <td>
                    <strong>{idx.dimension}D</strong>
                  </td>
                  <td>
                    <span className="ds-chunk-count">
                      <Layers size={14} />
                      {idx.document_count.toLocaleString()}개
                    </span>
                  </td>
                  <td>
                    <span className="ds-badge ds-badge--green" title="PostgreSQL 16 pgvector HNSW">
                      pgvector (LangChain)
                    </span>
                  </td>
                  <td>
                    <span className="ds-time-text">
                      <Clock size={12} /> {formatDate(idx.created_at)}
                    </span>
                  </td>
                  <td className="ds-text-right">
                    <div className="ds-actions-row">
                      <button
                        type="button"
                        className="ds-action-btn ds-action-btn--primary"
                        title="유사도 검색 테스트"
                        onClick={() => onSearchClick(idx)}
                      >
                        <Search size={14} />
                        <span>검색 테스트</span>
                      </button>
                      <button
                        type="button"
                        className="ds-action-btn"
                        title="청크 및 메타데이터 상세 보기"
                        onClick={() => onDetailClick(idx.index_id)}
                      >
                        <Eye size={14} />
                        <span>상세</span>
                      </button>
                      <button
                        type="button"
                        className="ds-action-btn ds-action-btn--danger"
                        title="인덱스 삭제"
                        onClick={() => onDeleteClick(idx.index_id)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
