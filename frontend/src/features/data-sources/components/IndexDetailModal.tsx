import { useEffect, useState } from 'react';
import { Database, Layers, Loader2, X } from 'lucide-react';
import { dataSourceApi } from '../services/dataSourceApi';
import type { VectorIndexDetail } from '../types';

interface DetailProps {
  indexId: string;
  onClose: () => void;
}

export function IndexDetailModal({ indexId, onClose }: DetailProps) {
  const [detail, setDetail] = useState<VectorIndexDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    dataSourceApi
      .getIndexDetail(indexId)
      .then((res) => {
        if (!cancelled) {
          setDetail(res);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || '인덱스 정보를 불러오지 못했습니다.');
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [indexId]);

  return (
    <div className="ds-modal-backdrop" onClick={onClose}>
      <div
        className="ds-modal ds-modal--large"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="index-detail-title"
      >
        <header className="ds-modal__header">
          <div className="ds-modal__title-wrap">
            <span className="ds-modal__icon ds-modal__icon--purple">
              <Database size={19} />
            </span>
            <div>
              <h3 id="index-detail-title">벡터 인덱스 상세 및 청크 미리보기</h3>
              <small className="ds-font-mono">{indexId.slice(0, 16)}...</small>
            </div>
          </div>
          <button className="ds-modal__close" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </button>
        </header>

        <div className="ds-modal__body">
          {isLoading && (
            <div className="ds-loading-state">
              <Loader2 className="ds-spin" size={24} />
              <span>인덱스 메타데이터를 로드하는 중...</span>
            </div>
          )}

          {error && <div className="ds-error-alert">{error}</div>}

          {!isLoading && !error && detail && (
            <div className="ds-index-detail-stack">
              {/* Meta stats bar */}
              <div className="ds-index-meta-bar">
                <div>
                  <small>원본 파일</small>
                  <strong>{detail.file_name}</strong>
                </div>
                <div>
                  <small>임베딩 모델</small>
                  <span className="ds-badge ds-badge--blue">{detail.model}</span>
                </div>
                <div>
                  <small>벡터 차원</small>
                  <strong>{detail.dimension}D</strong>
                </div>
                <div>
                  <small>저장된 청크 수</small>
                  <strong>{detail.document_count.toLocaleString()}개</strong>
                </div>
              </div>

              {/* Serialized chunks sample */}
              <div className="ds-chunks-section">
                <div className="ds-chunks-section__header">
                  <Layers size={16} />
                  <span>직렬화된 검색 청크 샘플 (상위 {detail.sample_items.length}개)</span>
                </div>

                <div className="ds-chunks-list">
                  {detail.sample_items.map((item, idx) => (
                    <div key={idx} className="ds-chunk-card">
                      <div className="ds-chunk-card__top">
                        <span className="ds-badge ds-badge--gray">{item.sheet_name}</span>
                        <span className="ds-font-mono ds-cell-coord">{item.cell_coord}</span>
                        <span className="ds-chunk-id">{item.cell_id}</span>
                      </div>
                      <div className="ds-chunk-card__text">{item.text}</div>
                      {(item.row_header.length > 0 || item.column_header.length > 0) && (
                        <div className="ds-chunk-card__headers">
                          {item.column_header.length > 0 && (
                            <small>
                              <strong>열 헤더:</strong> {item.column_header.join(' > ')}
                            </small>
                          )}
                          {item.row_header.length > 0 && (
                            <small>
                              <strong>행 헤더:</strong> {item.row_header.join(' > ')}
                            </small>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <footer className="ds-modal__footer">
          <button type="button" className="secondary-button" onClick={onClose}>
            닫기
          </button>
        </footer>
      </div>
    </div>
  );
}
