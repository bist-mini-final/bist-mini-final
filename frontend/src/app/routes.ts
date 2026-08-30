import {
  Bot,
  Boxes,
  ChartNoAxesCombined,
  Database,
  House,
  Scale,
  Settings,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { type ComponentType, lazy } from 'react';
import { ChatbotPage } from '../pages/ChatbotPage';
import { HomePage } from '../pages/HomePage';
import { SettingsPage } from '../pages/SettingsPage';

const CompanyComparisonPage = lazy(() =>
  import('../pages/CompanyComparisonPage').then((module) => ({ default: module.CompanyComparisonPage }))
);
const BiPage = lazy(() =>
  import('../pages/BiPage').then((module) => ({ default: module.BiPage }))
);
const PlaygroundPage = lazy(() =>
  import('../pages/PlaygroundPage').then((module) => ({
    default: module.PlaygroundPage,
  }))
);
const DataSourcesPage = lazy(() =>
  import('../pages/DataSourcesPage').then((module) => ({
    default: module.DataSourcesPage,
  }))
);
const JobsPage = lazy(() =>
  import('../pages/JobsPage').then((module) => ({ default: module.JobsPage }))
);

type RouteStatus = 'ready' | 'planned';

export interface AppRoute {
  path: string;
  label: string;
  shortLabel: string;
  description: string;
  icon: LucideIcon;
  component: ComponentType;
  status: RouteStatus;
}

/** Single route registry. Add a page here to expose it in routing and navigation. */
export const APP_ROUTES: readonly AppRoute[] = [
  {
    path: '/',
    label: '홈',
    shortLabel: 'Home',
    description: '서비스와 작업공간의 시작점',
    icon: House,
    component: HomePage,
    status: 'ready',
  },
  {
    path: '/playground',
    label: '플레이그라운드',
    shortLabel: 'Playground',
    description: '모듈을 조합하고 실행하는 실험 공간',
    icon: Workflow,
    component: PlaygroundPage,
    status: 'ready',
  },
  {
    path: '/data-sources',
    label: '데이터 소스',
    shortLabel: 'Data sources',
    description: '문서와 데이터셋을 관리하는 공간',
    icon: Database,
    component: DataSourcesPage,
    status: 'ready',
  },
  {
    path: '/dashboard',
    label: 'BI 대시보드',
    shortLabel: 'BI',
    description: '기업 재무 지표 및 인터랙티브 시각화 대시보드',
    icon: ChartNoAxesCombined,
    component: BiPage,
    status: 'ready',
  },
  {
    path: '/chatbot',
    label: 'AI 챗봇',
    shortLabel: 'Chatbot',
    description: '자연어로 질의하는 대화형 재무 비서',
    icon: Bot,
    component: ChatbotPage,
    status: 'ready',
  },
  {
    path: '/company-comparison',
    label: '기업 비교',
    shortLabel: 'Comparison',
    description: '검증된 BI 스냅샷 기반 기업 재무 순위 및 비교 분석',
    icon: Scale,
    component: CompanyComparisonPage,
    status: 'ready',
  },
  {
    path: '/jobs',
    label: '작업 관제',
    shortLabel: 'Jobs',
    description: 'KEDA ScaledJob, Job, Pod 읽기 전용 상태 관제',
    icon: Boxes,
    component: JobsPage,
    status: 'ready',
  },
  {
    path: '/settings',
    label: '설정',
    shortLabel: 'Settings',
    description: '데이터베이스 연결 및 시스템 환경 설정',
    icon: Settings,
    component: SettingsPage,
    status: 'ready',
  },
] as const;

/** Compatibility paths retained for links published by the architecture docs. */
export const ROUTE_ALIASES: Readonly<Record<string, string>> = {
  '/bi': '/dashboard',
};

export function findRoute(pathname: string): AppRoute | undefined {
  const canonicalPath = ROUTE_ALIASES[pathname] ?? pathname;
  return APP_ROUTES.find((route) => route.path === canonicalPath);
}
