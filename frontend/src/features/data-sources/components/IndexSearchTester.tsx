import { useState } from 'react';
import { Loader2, Search, Sparkles, X } from 'lucide-react';
import { Button, IconButton } from '../../../shared/ui';
import { dataSourceApi } from '../services/dataSourceApi';
import type { SearchResultItem } from '../types';

interface SearchTesterProps {
  indexId: string;
  fileName: string;
  model: string;
  onClose: () => void;
}

export function IndexSearchTester({ indexId, fileName, model, onClose }: SearchTesterProps) {
  const [query, setQuery] = useState('Total Revenue in 2024');
  const [limit, setLimit] = useState(5);
  const [results, setResults] = useState<SearchResultItem[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setError(null);
    try {
      const res = await dataSourceApi.searchIndex(indexId, query.trim(), limit);
      setResults(res.results);
    } catch (err: any) {
      setError(err.message || '유사도 검색 실행에 실패했습니다.');
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="ds-modal-backdrop" onClick={onClose}>
      <div
        className="ds-modal ds-modal--large"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="search-tester-title"
      >
        <header className="ds-modal__header">
          <div className="ds-modal__title-wrap">
            <span className="ds-modal__icon ds-modal__icon--green">
              <Search size={19} />
            </span>
            <div>
              <h3 id="search-tester-title">인덱스 유사도 검색 테스트</h3>
              <small>
                {fileName} · {model}
              </small>
            </div>
          </div>
          <IconButton variant="ghost" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </IconButton>
        </header>

        <div className="ds-modal__body">
          {/* Search Bar Form */}
          <form className="ds-search-form" onSubmit={handleSearch}>
            <div className="ds-search-input-wrap">
              <Search size={18} className="ds-search-icon" />
              <input
                type="text"
                className="ds-search-input"
                placeholder="테스트할 재무 질문 또는 키워드를 입력하세요 (예: 2024년 총 매출액)"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <select
              className="ds-select ds-select--small"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              <option value={3}>Top 3</option>
              <option value={5}>Top 5</option>
              <option value={10}>Top 10</option>
            </select>
            <Button
              variant="primary"
              type="submit"
              className="ds-search-btn"
              disabled={isSearching || !query.trim()}
            >
              {isSearching ? <Loader2 size={16} className="ds-spin" /> : '검색'}
            </Button>
          </form>

          {error && <div className="ds-error-alert">{error}</div>}

          {/* Search Results List */}
          <div className="ds-search-results">
            {isSearching && (
              <div className="ds-loading-state">
                <Loader2 className="ds-spin" size={24} />
                <span>벡터 유사도 연산 중...</span>
              </div>
            )}

            {!isSearching && results !== null && (
              <>
                <div className="ds-results-caption">
                  <Sparkles size={15} />
                  <span>
                    검색 결과 {results.length}건 (Cosine Similarity 내림차순)
                  </span>
                </div>

                {results.length === 0 ? (
                  <div className="ds-empty-box">일치하는 셀 문서가 없습니다.</div>
                ) : (
                  <div className="ds-results-list">
                    {results.map((hit, idx) => (
                      <div key={idx} className="ds-search-hit-card">
                        <div className="ds-search-hit-card__header">
                          <span className="ds-score-badge">
                            {(hit.score * 100).toFixed(1)}% 일치
                          </span>
                          <span className="ds-badge ds-badge--gray">{hit.sheet_name}</span>
                          <span className="ds-font-mono ds-cell-coord">{hit.cell_coord}</span>
                          {hit.cell_value && (
                            <span className="ds-hit-val">
                              값: <strong>{hit.cell_value}</strong>
                            </span>
                          )}
                        </div>
                        <div className="ds-hit-text">{hit.text}</div>
                        {(hit.row_header.length > 0 || hit.column_header.length > 0) && (
                          <div className="ds-hit-path">
                            {hit.column_header.join(' > ')}
                            {hit.column_header.length > 0 && hit.row_header.length > 0 && ' ∷ '}
                            {hit.row_header.join(' > ')}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <footer className="ds-modal__footer">
          <small>질의 벡터와 인덱스 벡터의 Inner Product(정규화 Cosine) 점수입니다.</small>
          <Button type="button" onClick={onClose}>
            닫기
          </Button>
        </footer>
      </div>
    </div>
  );
}
