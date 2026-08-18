import { Database, FileSpreadsheet, Layers, Sparkles } from 'lucide-react';
import type { DataSourceFile, VectorIndexInfo } from '../types';

interface SummaryProps {
  files: DataSourceFile[];
  indexes: VectorIndexInfo[];
}

export function DataSourcesSummary({ files, indexes }: SummaryProps) {
  const excelCount = files.filter((f) => f.file_type === 'excel').length;
  const totalChunks = indexes.reduce((sum, idx) => sum + (idx.document_count || 0), 0);
  const models = Array.from(new Set(indexes.map((i) => i.model)));

  return (
    <section className="ds-summary-grid">
      <div className="ds-summary-card">
        <div className="ds-summary-card__header">
          <span>원시 데이터 파일</span>
          <span className="ds-summary-card__icon ds-summary-card__icon--blue">
            <FileSpreadsheet size={17} />
          </span>
        </div>
        <div className="ds-summary-card__value">{files.length}<span>개</span></div>
        <small className="ds-summary-card__caption">
          Excel {excelCount}개 · 기타 {files.length - excelCount}개
        </small>
      </div>

      <div className="ds-summary-card">
        <div className="ds-summary-card__header">
          <span>구축된 벡터 인덱스</span>
          <span className="ds-summary-card__icon ds-summary-card__icon--green">
            <Database size={17} />
          </span>
        </div>
        <div className="ds-summary-card__value">{indexes.length}<span>개</span></div>
        <small className="ds-summary-card__caption">
          검색 파이프라인 연결 준비 완료
        </small>
      </div>

      <div className="ds-summary-card">
        <div className="ds-summary-card__header">
          <span>총 임베딩 청크 수</span>
          <span className="ds-summary-card__icon ds-summary-card__icon--purple">
            <Layers size={17} />
          </span>
        </div>
        <div className="ds-summary-card__value">
          {totalChunks.toLocaleString()}<span>청크</span>
        </div>
        <small className="ds-summary-card__caption">
          셀 단위 4필드 직렬화 검색 데이터
        </small>
      </div>

      <div className="ds-summary-card">
        <div className="ds-summary-card__header">
          <span>사용 중인 모델</span>
          <span className="ds-summary-card__icon ds-summary-card__icon--amber">
            <Sparkles size={17} />
          </span>
        </div>
        <div className="ds-summary-card__value ds-summary-card__value--text">
          {models.length > 0 ? models[0].split('/').pop() : '미등록'}
        </div>
        <small className="ds-summary-card__caption">
          {models.length > 1 ? `외 ${models.length - 1}개 모델` : 'OpenAI / BGE 고밀도 임베딩'}
        </small>
      </div>
    </section>
  );
}
