import {
  ArrowRight,
  BarChart3,
  Bot,
  CheckCircle2,
  Database,
  FileSearch,
  FileSpreadsheet,
  LayoutDashboard,
  MessageSquareText,
  Scale,
  ScanSearch,
  Sparkles,
  Waypoints,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { AppLink } from '../app/router';
import './HomePage.css';

interface JourneyStep {
  readonly number: string;
  readonly title: string;
  readonly description: string;
  readonly action: string;
  readonly path: string;
  readonly icon: LucideIcon;
}

interface WorkspaceLink {
  readonly path: string;
  readonly eyebrow: string;
  readonly title: string;
  readonly description: string;
  readonly action: string;
  readonly tone: 'green' | 'blue' | 'violet' | 'indigo' | 'cyan';
  readonly icon: LucideIcon;
  readonly featured?: boolean;
}

const journeySteps: readonly JourneyStep[] = [
  {
    number: '01',
    title: 'Excel 원본 적재',
    description: '재무 Excel을 업로드하고 기업명과 인덱싱 상태를 확인합니다.',
    action: '데이터 소스 열기',
    path: '/data-sources',
    icon: FileSpreadsheet,
  },
  {
    number: '02',
    title: '워크플로 검증',
    description: '표준 RAG 파이프라인의 모듈별 입력·출력과 실행 흐름을 검증합니다.',
    action: '플레이그라운드 열기',
    path: '/playground',
    icon: Workflow,
  },
  {
    number: '03',
    title: '기업 스냅샷 생성',
    description: '적재된 기업을 선택해 BI 분석용 스냅샷을 생성하고 갱신합니다.',
    action: 'BI 대시보드 열기',
    path: '/dashboard',
    icon: LayoutDashboard,
  },
  {
    number: '04',
    title: '질문하고 근거 확인',
    description: '재무 질문의 답변과 셀 근거를 원본 시트 이미지에서 확인합니다.',
    action: 'AI 챗봇 열기',
    path: '/chatbot',
    icon: MessageSquareText,
  },
];

const workspaceLinks: readonly WorkspaceLink[] = [
  {
    path: '/playground',
    eyebrow: 'BUILD & OBSERVE',
    title: '플레이그라운드',
    description: '모듈을 조합하고 Kubernetes DAG의 실행 상태와 각 단계 결과를 관찰합니다.',
    action: '워크플로 열기',
    tone: 'green',
    icon: Workflow,
    featured: true,
  },
  {
    path: '/data-sources',
    eyebrow: 'INGEST & INDEX',
    title: '데이터 소스',
    description: 'Excel 파일, 기업 메타데이터, pgvector 인덱스와 적재 작업을 관리합니다.',
    action: '데이터 관리',
    tone: 'blue',
    icon: Database,
  },
  {
    path: '/dashboard',
    eyebrow: 'ANALYZE',
    title: 'BI 대시보드',
    description: '기업별 재무 스냅샷을 카드와 시계열 차트로 분석합니다.',
    action: '대시보드 열기',
    tone: 'violet',
    icon: BarChart3,
  },
  {
    path: '/chatbot',
    eyebrow: 'ASK & VERIFY',
    title: 'AI 금융 챗봇',
    description: '대화형 재무 답변을 받고 인용 셀을 원본 시트에서 검증합니다.',
    action: '새 질문 시작',
    tone: 'indigo',
    icon: Bot,
  },
  {
    path: '/company-comparison',
    eyebrow: 'COMPARE',
    title: '기업 비교',
    description: '여러 기업의 성장성·수익성·안정성을 동일한 기준으로 비교합니다.',
    action: '기업 비교 열기',
    tone: 'cyan',
    icon: Scale,
  },
];

const analysisFlow = [
  { label: 'Excel', detail: '원본 데이터', icon: FileSpreadsheet },
  { label: 'Structure', detail: '셀 계층 인식', icon: ScanSearch },
  { label: 'Retrieve', detail: '하이브리드 검색', icon: Waypoints },
  { label: 'Evidence', detail: '원본 셀 검증', icon: FileSearch },
] as const;

/** Product onboarding hub for first-time and returning users. */
export function HomePage() {
  return (
    <div className="home-onboarding">
      <section className="home-onboarding__hero" aria-labelledby="home-title">
        <div className="home-onboarding__intro">
          <div className="home-onboarding__eyebrow">
            <Sparkles aria-hidden="true" />
            <span>FINANCIAL RAG WORKSPACE</span>
          </div>
          <h1 id="home-title">재무 Excel을 올리고,<br />근거까지 검증하세요.</h1>
          <p>
            비정형 스프레드시트를 셀 단위로 구조화하고 검색·분석·비교·질의까지
            하나의 검증 가능한 흐름으로 연결합니다.
          </p>
          <div className="home-onboarding__actions" aria-label="빠른 시작">
            <AppLink to="/data-sources" className="home-onboarding__primary-action">
              <FileSpreadsheet aria-hidden="true" />
              Excel 데이터 추가
              <ArrowRight aria-hidden="true" />
            </AppLink>
            <AppLink to="/playground" className="home-onboarding__secondary-action">
              <Workflow aria-hidden="true" />
              플레이그라운드 열기
            </AppLink>
          </div>
          <ul className="home-onboarding__capabilities" aria-label="핵심 기능">
            <li><CheckCircle2 aria-hidden="true" /> 셀 계층 구조 보존</li>
            <li><CheckCircle2 aria-hidden="true" /> pgvector + 키워드 검색</li>
            <li><CheckCircle2 aria-hidden="true" /> 원본 시트 근거 검증</li>
          </ul>
        </div>

        <aside className="home-flow" aria-label="재무 데이터 분석 흐름">
          <header className="home-flow__header">
            <div>
              <span>END-TO-END FLOW</span>
              <strong>원본부터 검증 가능한 답변까지</strong>
            </div>
            <span className="home-flow__status"><i /> 4 stages</span>
          </header>
          <ol className="home-flow__steps">
            {analysisFlow.map(({ label, detail, icon: Icon }, index) => (
              <li key={label}>
                <span className="home-flow__icon"><Icon aria-hidden="true" /></span>
                <div><strong>{label}</strong><small>{detail}</small></div>
                {index < analysisFlow.length - 1 && <ArrowRight aria-hidden="true" />}
              </li>
            ))}
          </ol>
          <div className="home-flow__result">
            <span><FileSearch aria-hidden="true" /></span>
            <div>
              <small>ANSWER TRACE</small>
              <strong>Sheet · Cell 좌표까지 추적</strong>
              <p>근거 뱃지를 클릭해 실제 Excel 시트의 원본 셀을 확인할 수 있습니다.</p>
            </div>
          </div>
        </aside>
      </section>

      <section className="home-onboarding__section" aria-labelledby="journey-title">
        <header className="home-onboarding__section-heading">
          <div>
            <span>QUICK START</span>
            <h2 id="journey-title">처음이라면 이렇게 시작하세요</h2>
          </div>
          <p>데이터 준비부터 답변 검증까지 권장 순서입니다.</p>
        </header>
        <ol className="home-journey">
          {journeySteps.map(({ number, title, description, action, path, icon: Icon }) => (
            <li key={number}>
              <AppLink to={path} className="home-journey__card">
                <div className="home-journey__topline">
                  <span className="home-journey__icon"><Icon aria-hidden="true" /></span>
                  <b>{number}</b>
                </div>
                <strong>{title}</strong>
                <p>{description}</p>
                <span className="home-journey__action">{action}<ArrowRight aria-hidden="true" /></span>
              </AppLink>
            </li>
          ))}
        </ol>
      </section>

      <section className="home-onboarding__section" aria-labelledby="workspace-title">
        <header className="home-onboarding__section-heading">
          <div>
            <span>WORKSPACES</span>
            <h2 id="workspace-title">목적에 맞는 작업 공간으로 이동하세요</h2>
          </div>
          <p>5개 작업 공간을 모두 사용할 수 있습니다.</p>
        </header>
        <div className="home-workspaces">
          {workspaceLinks.map(({ path, eyebrow, title, description, action, tone, icon: Icon, featured }) => (
            <AppLink
              key={path}
              to={path}
              className={`home-workspace home-workspace--${tone}${featured ? ' home-workspace--featured' : ''}`}
            >
              <span className="home-workspace__icon"><Icon aria-hidden="true" /></span>
              <div className="home-workspace__copy">
                <span>{eyebrow}</span>
                <strong>{title}</strong>
                <p>{description}</p>
              </div>
              <span className="home-workspace__action">{action}<ArrowRight aria-hidden="true" /></span>
            </AppLink>
          ))}
        </div>
      </section>
    </div>
  );
}
