import {
  ArrowRight,
  ChartNoAxesCombined,
  Database,
  FileCode2,
  Workflow,
} from 'lucide-react';
import { AppLink } from '../app/router';

const plannedCards = [
  {
    path: '/data-sources',
    title: '데이터 소스',
    description: '문서와 인덱스 자산을 한곳에서 관리합니다.',
    icon: Database,
    tone: 'blue',
  },
  {
    path: '/evaluations',
    title: '평가',
    description: '정확도와 실행 비용을 실험별로 비교합니다.',
    icon: ChartNoAxesCombined,
    tone: 'amber',
  },
  {
    path: '/bi',
    title: 'BI',
    description: 'BI 기능을 위한 독립 화면을 구성합니다.',
    icon: ChartNoAxesCombined,
    tone: 'violet',
  },
] as const;

export function HomePage() {
  return (
    <div className="home-page">
      <section className="home-section" aria-labelledby="workspace-title">
        <div className="home-section__heading">
          <div>
            <span>WORKSPACE</span>
            <h2 id="workspace-title">작업 공간</h2>
          </div>
          <small>1개 사용 가능 · 3개 준비 중</small>
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

      <section className="home-bottom-grid">
        <article className="home-info-card">
          <span className="home-info-card__icon"><FileCode2 size={19} /></span>
          <div>
            <small>DEVELOPER CONTRACT</small>
            <h3>모든 모듈은 독립 JSON API입니다</h3>
            <p>Input, Config, Output DTO를 ReDoc에서 확인하고 프론트 없이도 실행할 수 있습니다.</p>
          </div>
          <a href="/redoc" target="_blank" rel="noreferrer">API 문서 보기 <ArrowRight size={15} /></a>
        </article>
        <article className="home-info-card home-info-card--dark">
          <span className="home-info-card__icon"><Workflow size={19} /></span>
          <div>
            <small>QUICK START</small>
            <h3>연결만으로 워크플로 완성</h3>
            <p>상류 Output 포트를 하류 Input 포트에 연결하면 실행 순서와 데이터 계보가 보존됩니다.</p>
          </div>
          <AppLink to="/playground">실험 시작하기 <ArrowRight size={15} /></AppLink>
        </article>
      </section>
    </div>
  );
}
