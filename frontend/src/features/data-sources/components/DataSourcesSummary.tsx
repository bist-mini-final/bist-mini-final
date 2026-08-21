import { Database, Layers, Server, Sparkles } from 'lucide-react';
import type { DbStatusInfo, VectorIndexInfo } from '../types';

interface SummaryProps {
  indexes: VectorIndexInfo[];
  dbStatus: DbStatusInfo | null;
}

/**
 * Renders a summary of vector data sources, embedding usage, database status, and models.
 *
 * @param indexes - Vector data source indexes to summarize
 * @param dbStatus - Current database connection and pgvector status
 */
export function DataSourcesSummary({ indexes, dbStatus }: SummaryProps) {
  const totalChunks = indexes.reduce((sum, idx) => sum + (idx.document_count || 0), 0);
  const models = Array.from(new Set(indexes.map((i) => i.model).filter(Boolean)));

  return (
    <section className="ds-summary-grid">
      <div className="ds-summary-card">
        <div className="ds-summary-card__header">
          <span>pgvector 컬렉션</span>
          <span className="ds-summary-card__icon ds-summary-card__icon--blue">
            <Database size={17} />
          </span>
        </div>
        <div className="ds-summary-card__value">{indexes.length}<span>개</span></div>
        <small className="ds-summary-card__caption">
          langchain_pg_collection 등록
        </small>
      </div>

      <div className="ds-summary-card">
        <div className="ds-summary-card__header">
          <span>총 벡터 임베딩 청크</span>
          <span className="ds-summary-card__icon ds-summary-card__icon--green">
            <Layers size={17} />
          </span>
        </div>
        <div className="ds-summary-card__value">{totalChunks.toLocaleString()}<span>청크</span></div>
        <small className="ds-summary-card__caption">
          langchain_pg_embedding 저장
        </small>
      </div>

      <div className="ds-summary-card">
        <div className="ds-summary-card__header">
          <span>데이터베이스 엔진</span>
          <span className="ds-summary-card__icon ds-summary-card__icon--purple">
            <Server size={17} />
          </span>
        </div>
        <div className="ds-summary-card__value ds-summary-card__value--text">
          {dbStatus?.connected ? 'PostgreSQL 16' : '연결 대기 중'}
        </div>
        <small className="ds-summary-card__caption">
          {dbStatus?.connected
            ? `pgvector ${dbStatus.pgvector_version || '0.8.6'} · HNSW 인덱싱`
            : 'deploy/db/docker-compose.yml 실행 필요'}
        </small>
      </div>

      <div className="ds-summary-card">
        <div className="ds-summary-card__header">
          <span>임베딩 표준 모델</span>
          <span className="ds-summary-card__icon ds-summary-card__icon--amber">
            <Sparkles size={17} />
          </span>
        </div>
        <div className="ds-summary-card__value ds-summary-card__value--text">
          {models.length > 0 ? models[0].split('/').pop() : 'text-embedding-3-large'}
        </div>
        <small className="ds-summary-card__caption">
          {models.length > 1 ? `외 ${models.length - 1}개 모델 사용 중` : '3072차원 고밀도 벡터 공간'}
        </small>
      </div>
    </section>
  );
}
