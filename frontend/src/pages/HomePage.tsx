import {
  ArrowRight,
  BarChart3,
  Bot,
  ChartNoAxesCombined,
  Database,
  FileSpreadsheet,
  Scale,
  Sparkles,
  TrendingUp,
  Workflow,
} from 'lucide-react';
import { AppLink } from '../app/router';

const secondaryCards = [
  {
    path: '/chatbot',
    title: 'AI 금융 챗봇',
    description: '자연어로 질의하고 실시간 재무 데이터 기반의 정확한 인사이트와 답변을 제공받습니다.',
    icon: Bot,
    tone: 'indigo',
  },
  {
    path: '/company-comparison',
    title: '기업 비교 대시보드',
    description: 'IBM, Bistelligence, DH Innovation 등 다중 기업 간의 재무 비율과 성장성을 크로스 비교합니다.',
    icon: Scale,
    tone: 'cyan',
  },
] as const;

/**
 * Renders the workspace landing page with links to available and upcoming workspaces.
 */
export function HomePage() {
  return (
    <div className="home-page">
      <section className="home-hero" aria-labelledby="home-hero-title">
        <div>
          <div className="home-eyebrow">
            <Sparkles size={13} />
            <span>AI FINANCIAL INTELLIGENCE PLATFORM</span>
          </div>
          <h1 id="home-hero-title">
            엑셀 구조화부터 지능형 금융 RAG까지
          </h1>
          <p>
            비정형 스프레드시트의 셀 구조를 VLM으로 분석하고, 인덱스별 차원이 보장된 pgvector와
            Kubernetes DAG 파이프라인으로 빠른 재무 분석 및 근거 기반 답변을 제공합니다.
          </p>
        </div>
      </section>

      <section className="home-section" aria-labelledby="workspace-title">
        <div className="home-section__heading">
          <div>
            <span>WORKSPACES</span>
            <h2 id="workspace-title">작업 공간</h2>
          </div>
          <small>5개 작업공간 사용 가능</small>
        </div>

        <div className="workspace-grid">
          {/* 1. Pipeline Playground */}
          <AppLink to="/playground" className="workspace-card workspace-card--featured">
            <div className="playground-preview" aria-hidden="true">
              <span className="preview-glow preview-glow--one" />
              <span className="preview-glow preview-glow--two" />
              <div className="preview-node preview-node--query">
                <span>01</span><strong>Query</strong><small>질문 입력 & 분해</small>
              </div>
              <div className="preview-path preview-path--one" />
              <div className="preview-node preview-node--retrieval">
                <span>02</span><strong>Retrieve</strong><small>pgvector RRF 검색</small>
              </div>
              <div className="preview-path preview-path--two" />
              <div className="preview-node preview-node--reader">
                <span>03</span><strong>Reader</strong><small>수식 & 정제 답변</small>
              </div>
            </div>
            <div className="workspace-card__footer">
              <span className="workspace-card__icon workspace-card__icon--green">
                <Workflow size={18} />
              </span>
              <div>
                <strong>Pipeline Playground</strong>
                <small>모듈을 조합하고 제로 I/O 인메모리로 즉시 실행</small>
              </div>
              <span className="workspace-card__action"><ArrowRight size={17} /></span>
            </div>
          </AppLink>

          {/* 2. Data Sources & pgvector */}
          <AppLink to="/data-sources" className="workspace-card">
            <div className="datasources-preview" aria-hidden="true">
              <span className="preview-glow preview-glow--blue-one" />
              <span className="preview-glow preview-glow--blue-two" />
              <div className="ds-preview-container">
                <div className="ds-preview-card">
                  <div className="ds-preview-card__header">
                    <div className="ds-preview-card__header-left">
                      <FileSpreadsheet size={13} style={{ color: '#2563eb' }} />
                      <span>Luna VLM 구조화</span>
                    </div>
                    <span className="ds-preview-card__badge">Table Bounds</span>
                  </div>
                  <div className="ds-preview-card__items">
                    <span>[SHEET] KeyStats / IS</span>
                    <span>[COL] Total Revenue 2024</span>
                    <span>[VAL] $62,472M (Audited)</span>
                  </div>
                </div>

                <div className="ds-preview-connector">
                  <span className="ds-preview-connector__pill">
                    <Sparkles size={9} /> INDEX-BOUND
                  </span>
                  <ArrowRight size={14} />
                </div>

                <div className="ds-preview-card">
                  <div className="ds-preview-card__header">
                    <div className="ds-preview-card__header-left">
                      <Database size={13} style={{ color: '#4f46e5' }} />
                      <span>PostgreSQL pgvector</span>
                    </div>
                    <span className="ds-preview-card__badge">HNSW</span>
                  </div>
                  <div className="ds-preview-card__items">
                    <span style={{ color: '#2563eb', fontWeight: 700 }}>Cosine sim: 0.988</span>
                    <span>Multi-Company Collections</span>
                    <span>Native Full-Text + Vector</span>
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

          {/* 3. BI Financial Dashboard */}
          <AppLink to="/dashboard" className="workspace-card">
            <div className="dashboard-preview" aria-hidden="true">
              <span className="preview-glow preview-glow--violet-one" />
              <span className="preview-glow preview-glow--violet-two" />
              <div className="bi-preview-container">
                <div className="bi-preview-card">
                  <div className="bi-preview-card__header">
                    <div className="bi-preview-card__header-left">
                      <TrendingUp size={13} style={{ color: '#7c3aed' }} />
                      <span>매출 & 영업이익 추이</span>
                    </div>
                    <span className="bi-preview-card__badge">Growth</span>
                  </div>
                  <div className="bi-preview-bars">
                    <div className="bi-preview-bar" style={{ height: '40%' }} />
                    <div className="bi-preview-bar" style={{ height: '55%' }} />
                    <div className="bi-preview-bar" style={{ height: '70%' }} />
                    <div className="bi-preview-bar" style={{ height: '85%' }} />
                    <div className="bi-preview-bar" style={{ height: '100%' }} />
                  </div>
                </div>

                <div className="bi-preview-card">
                  <div className="bi-preview-card__header">
                    <div className="bi-preview-card__header-left">
                      <BarChart3 size={13} style={{ color: '#9333ea' }} />
                      <span>재무 건전성 분석</span>
                    </div>
                    <span className="bi-preview-card__badge">3개사 통합</span>
                  </div>
                  <div className="ds-preview-card__items">
                    <span style={{ color: '#7c3aed', fontWeight: 700 }}>영업이익률: 14.8%</span>
                    <span>부채비율: 78.2% (안정)</span>
                    <span>ROE / ROA 실시간 산출</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="workspace-card__footer">
              <span className="workspace-card__icon workspace-card__icon--violet">
                <ChartNoAxesCombined size={18} />
              </span>
              <div>
                <strong>BI 재무 대시보드</strong>
                <small>기업별 재무제표 탐색 및 인터랙티브 인터페이스</small>
              </div>
              <span className="workspace-card__action"><ArrowRight size={17} /></span>
            </div>
          </AppLink>

          {/* Secondary workspace cards */}
          {secondaryCards.map(({ path, title, description, icon: Icon, tone }) => (
            <AppLink key={path} to={path} className="workspace-card">
              <div className={`planned-preview planned-preview--${tone}`}>
                <span className="planned-preview__badge">AVAILABLE</span>
                <Icon size={34} strokeWidth={1.45} />
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
