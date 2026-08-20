import {
  ArrowRight,
  ChartNoAxesCombined,
  Database,
  FileSpreadsheet,
  Sparkles,
  Workflow,
} from 'lucide-react';
import { AppLink } from '../app/router';

const plannedCards = [
  {
    path: '/evaluations',
    title: '평가',
    description: '정확도와 실행 비용을 실험별로 비교합니다.',
    icon: ChartNoAxesCombined,
    tone: 'amber',
  },
  {
    path: '/dashboard',
    title: 'Dashboard',
    description: '기업 재무 대시보드를 확인합니다.',
    icon: ChartNoAxesCombined,
    tone: 'violet',
  },
] as const;

/**
 * Renders the workspace landing page with links to available and upcoming workspaces.
 */
export function HomePage() {
  return (
    <div className="home-page">
      <section className="home-section" aria-labelledby="workspace-title">
        <div className="home-section__heading">
          <div>
            <span>WORKSPACE</span>
            <h2 id="workspace-title">작업 공간</h2>
          </div>
          <small>2개 사용 가능 · 2개 준비 중</small>
        </div>

        <div className="workspace-grid">
          <AppLink to="/playground" className="workspace-card workspace-card--featured">
            <div className="playground-preview" aria-hidden="true">
              <span className="preview-glow preview-glow--one" />
              <span className="preview-glow preview-glow--two" />
              <div className="preview-node preview-node--query">
                <span>01</span><strong>Query</strong><small>질문 입력</small>
              </div>
              <div className="preview-path preview-path--one" />
              <div className="preview-node preview-node--retrieval">
                <span>02</span><strong>Retrieve</strong><small>문서 검색</small>
              </div>
              <div className="preview-path preview-path--two" />
              <div className="preview-node preview-node--reader">
                <span>03</span><strong>Reader</strong><small>답변 생성</small>
              </div>
            </div>
            <div className="workspace-card__footer">
              <span className="workspace-card__icon workspace-card__icon--green">
                <Workflow size={18} />
              </span>
              <div>
                <strong>Pipeline Playground</strong>
                <small>모듈을 조합하고 즉시 실행</small>
              </div>
              <span className="workspace-card__action"><ArrowRight size={17} /></span>
            </div>
          </AppLink>

          <AppLink to="/data-sources" className="workspace-card">
            <div className="datasources-preview" aria-hidden="true">
              <span className="preview-glow preview-glow--blue-one" />
              <span className="preview-glow preview-glow--blue-two" />
              <div className="ds-preview-container">
                {/* Left Card: Ingestion / Chunk */}
                <div className="ds-preview-card">
                  <div className="ds-preview-card__header">
                    <div className="ds-preview-card__header-left">
                      <FileSpreadsheet size={13} style={{ color: '#2563eb' }} />
                      <span>Luna VLM 청킹</span>
                    </div>
                    <span className="ds-preview-card__badge">4-Field</span>
                  </div>
                  <div className="ds-preview-card__items">
                    <span>[SHEET] KeyStats</span>
                    <span>[COL] 매출액 / 2024</span>
                    <span>[VALUE] 1,240억원</span>
                  </div>
                </div>

                {/* Center Connector */}
                <div className="ds-preview-connector">
                  <span className="ds-preview-connector__pill">
                    <Sparkles size={9} /> 3072D
                  </span>
                  <ArrowRight size={14} />
                </div>

                {/* Right Card: Vector Store */}
                <div className="ds-preview-card">
                  <div className="ds-preview-card__header">
                    <div className="ds-preview-card__header-left">
                      <Database size={13} style={{ color: '#4f46e5' }} />
                      <span>pgvector DB</span>
                    </div>
                    <span className="ds-preview-card__badge">HNSW</span>
                  </div>
                  <div className="ds-preview-card__items">
                    <span style={{ color: '#2563eb', fontWeight: 700 }}>sim: 0.985 (Match)</span>
                    <span>table: langchain_pg</span>
                    <span>dim: 3072 Cosine</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="workspace-card__footer">
              <span className="workspace-card__icon workspace-card__icon--blue">
                <Database size={18} />
              </span>
              <div>
                <strong>데이터 소스 & pgvector</strong>
                <small>엑셀 구조화 및 고밀도 벡터 인덱스 관리</small>
              </div>
              <span className="workspace-card__action"><ArrowRight size={17} /></span>
            </div>
          </AppLink>

          {plannedCards.map(({ path, title, description, icon: Icon, tone }) => (
            <AppLink key={path} to={path} className="workspace-card workspace-card--planned">
              <div className={`planned-preview planned-preview--${tone}`}>
                <span className="planned-preview__badge">COMING SOON</span>
                <Icon size={32} strokeWidth={1.45} />
              </div>
              <div className="workspace-card__footer">
                <span className={`workspace-card__icon workspace-card__icon--${tone}`}>
                  <Icon size={18} />
                </span>
                <div>
                  <strong>{title}</strong>
                  <small>{description}</small>
                </div>
                <span className="workspace-card__action"><ArrowRight size={17} /></span>
              </div>
            </AppLink>
          ))}
        </div>
      </section>
    </div>
  );
}
