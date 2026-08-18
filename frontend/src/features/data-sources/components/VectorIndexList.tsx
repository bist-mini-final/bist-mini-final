import {
  Clock,
  Database,
  Eye,
  Layers,
  Search,
  Sparkles,
  Trash2,
} from 'lucide-react';
import type { VectorIndexInfo } from '../types';

interface VectorIndexListProps {
  indexes: VectorIndexInfo[];
  onDetailClick: (indexId: string) => void;
  onSearchClick: (index: VectorIndexInfo) => void;
  onDeleteClick: (indexId: string) => void;
  onCreateClick: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
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
  onDetailClick,
  onSearchClick,
  onDeleteClick,
  onCreateClick,
}: VectorIndexListProps) {
  return (
    <div className="ds-panel">
      <div className="ds-panel__header">
        <div>
          <h3>영속 벡터 DB 인덱스 목록</h3>
          <small>data/vector_db/에 저장된 고밀도 Cosine 임베딩 인덱스 (.npy + .json)</small>
        </div>
        <button type="button" className="primary-button" onClick={onCreateClick}>
          <Sparkles size={15} /> 새 인덱스 생성
        </button>
      </div>

      {indexes.length === 0 ? (
        <div className="ds-empty-state">
          <Database size={40} />
          <h4>구축된 벡터 인덱스가 없습니다</h4>
          <p>엑셀 파일에서 텍스트를 직렬화하고 임베딩하여 첫 번째 벡터 인덱스를 구축해보세요.</p>
          <button type="button" className="primary-button" onClick={onCreateClick}>
            <Sparkles size={15} /> 엑셀 인덱싱 시작
          </button>
        </div>
      ) : (
        <div className="ds-table-container">
          <table className="ds-table">
            <thead>
              <tr>
                <th>인덱스 ID</th>
                <th>원본 파일</th>
                <th>임베딩 모델</th>
                <th>차원</th>
                <th>저장된 청크 수</th>
                <th>인덱스 크기</th>
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
                    <strong>{idx.file_name}</strong>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <span className="ds-badge ds-badge--blue">{idx.model}</span>
                      {idx.storage === 'pgvector' && (
                        <span className="ds-badge ds-badge--green" title="PostgreSQL pgvector 적재됨">
                          pgvector
                        </span>
                      )}
                    </div>
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
                  <td>{formatBytes(idx.total_size_bytes || 0)}</td>
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
