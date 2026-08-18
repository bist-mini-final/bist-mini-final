import { useState } from 'react';
import {
  Building2,
  Check,
  Clock,
  Cpu,
  Database,
  Edit2,
  Eye,
  Layers,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import type { VectorIndexInfo } from '../types';
import { dataSourceApi } from '../services/dataSourceApi';

interface VectorIndexListProps {
  indexes: VectorIndexInfo[];
  isLoading?: boolean;
  onRefresh?: () => void;
  onDetailClick: (indexId: string) => void;
  onSearchClick: (index: VectorIndexInfo) => void;
  onDeleteClick: (indexId: string) => void;
  onCreateClick: () => void;
  onPipelineLogClick?: (index: VectorIndexInfo) => void;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${yyyy}.${mm}.${dd} ${hh}:${min}`;
  } catch {
    return iso;
  }
}

export function VectorIndexList({
  indexes,
  isLoading,
  onRefresh,
  onDetailClick,
  onSearchClick,
  onDeleteClick,
  onCreateClick,
  onPipelineLogClick,
}: VectorIndexListProps) {
  const [editingIndexId, setEditingIndexId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const startEditCompany = (idx: VectorIndexInfo) => {
    setEditingIndexId(idx.index_id);
    setEditingName(idx.company_name || idx.file_name?.replace(/\.[^/.]+$/, '') || '');
  };

  const cancelEdit = () => {
    setEditingIndexId(null);
    setEditingName('');
  };

  const saveCompany = async (indexId: string) => {
    const trimmed = editingName.trim();
    if (!trimmed) {
      cancelEdit();
      return;
    }
    setIsSaving(true);
    try {
      await dataSourceApi.updateIndexCompany(indexId, trimmed);
      setEditingIndexId(null);
      setEditingName('');
      onRefresh?.();
    } catch (err: any) {
      alert(err.message || '기업명 수정에 실패했습니다.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="ds-panel">
      <div className="ds-panel__header">
        <div>
          <h3>PostgreSQL pgvector 컬렉션 목록</h3>
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
                <th style={{ width: '120px' }}>컬렉션 ID</th>
                <th>대상 데이터셋</th>
                <th style={{ width: '200px' }}>기업명 (Company)</th>
                <th style={{ width: '150px' }}>임베딩 모델</th>
                <th style={{ width: '70px' }}>차원</th>
                <th style={{ width: '130px' }}>저장된 청크 수</th>
                <th style={{ width: '120px' }}>스토리지</th>
                <th style={{ width: '130px' }}>생성일시</th>
                <th className="ds-text-right" style={{ width: '270px' }}>작업</th>
              </tr>
            </thead>
            <tbody>
              {indexes.map((idx) => {
                const isEditingThis = editingIndexId === idx.index_id;
                const companyDisplay = idx.company_name || '';

                return (
                  <tr key={idx.index_id}>
                    <td className="ds-font-mono ds-id-cell" style={{ whiteSpace: 'nowrap' }}>
                      <span title={idx.index_id}>{idx.index_id.slice(0, 10)}...</span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap', fontWeight: 650, color: '#0f172a' }}>
                      {idx.file_name || 'Dataset'}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div className="ds-company-cell">
                        {isEditingThis ? (
                          <div className="ds-company-inline-form">
                            <input
                              type="text"
                              className="ds-company-inline-input"
                              value={editingName}
                              onChange={(e) => setEditingName(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') saveCompany(idx.index_id);
                                else if (e.key === 'Escape') cancelEdit();
                              }}
                              placeholder="기업명 입력..."
                              autoFocus
                              disabled={isSaving}
                            />
                            <button
                              type="button"
                              className="ds-company-inline-save"
                              title="저장 (Enter)"
                              onClick={() => saveCompany(idx.index_id)}
                              disabled={isSaving}
                            >
                              <Check size={12} />
                            </button>
                            <button
                              type="button"
                              className="ds-company-inline-cancel"
                              title="취소 (Esc)"
                              onClick={cancelEdit}
                              disabled={isSaving}
                            >
                              <X size={12} />
                            </button>
                          </div>
                        ) : (
                          <>
                            <span
                              className={`ds-company-badge ${!companyDisplay ? 'ds-company-badge--empty' : ''}`}
                              title="클릭하여 기업명 수정"
                              onClick={() => startEditCompany(idx)}
                            >
                              <Building2 size={12} style={{ color: companyDisplay ? '#166534' : '#94a3b8' }} />
                              <span>{companyDisplay || '+ 기업명 입력'}</span>
                            </span>
                            <button
                              type="button"
                              className="ds-company-edit-btn"
                              title="기업명 수정"
                              onClick={() => startEditCompany(idx)}
                            >
                              <Edit2 size={12} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="ds-model-badge" title={idx.model}>
                        {idx.model}
                      </span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="ds-dim-pill">{idx.dimension}D</span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div className="ds-chunk-block">
                        <div className="ds-chunk-primary">
                          <Layers size={13} style={{ color: '#0f766e' }} />
                          <span>{idx.document_count.toLocaleString()}개</span>
                        </div>
                        {idx.duration_seconds !== undefined && idx.duration_seconds !== null && (
                          <div className="ds-chunk-subtext">
                            ⏱️ {idx.duration_seconds}s {idx.estimated_cost_usd ? `· $${idx.estimated_cost_usd.toFixed(4)}` : ''}
                          </div>
                        )}
                      </div>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="ds-badge ds-badge--green" title="PostgreSQL 16 pgvector HNSW">
                        pgvector (LangChain)
                      </span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="ds-time-text">
                        <Clock size={12} /> {formatDate(idx.created_at)}
                      </span>
                    </td>
                    <td className="ds-text-right" style={{ whiteSpace: 'nowrap' }}>
                      <div className="ds-actions-row">
                        <button
                          type="button"
                          className="ds-action-btn"
                          title="4대 모듈 파이프라인 실행 로그 및 세부 단계 확인"
                          onClick={() => onPipelineLogClick?.(idx)}
                        >
                          <Cpu size={13} />
                          <span>모듈 로그</span>
                        </button>
                        <button
                          type="button"
                          className="ds-action-btn ds-action-btn--primary"
                          title="유사도 검색 테스트"
                          onClick={() => onSearchClick(idx)}
                        >
                          <Search size={13} />
                          <span>검색 테스트</span>
                        </button>
                        <button
                          type="button"
                          className="ds-action-btn"
                          title="청크 및 메타데이터 상세 보기"
                          onClick={() => onDetailClick(idx.index_id)}
                        >
                          <Eye size={13} />
                          <span>상세</span>
                        </button>
                        <button
                          type="button"
                          className="ds-action-btn ds-action-btn--danger"
                          title="인덱스 삭제"
                          onClick={() => onDeleteClick(idx.index_id)}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
