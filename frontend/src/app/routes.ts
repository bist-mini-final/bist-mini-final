import {
  ChartNoAxesCombined,
  Database,
  House,
  Settings,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { type ComponentType, lazy } from 'react';
import { DataSourcesPage } from '../pages/DataSourcesPage';
import { EvaluationsPage } from '../pages/EvaluationsPage';
import { HomePage } from '../pages/HomePage';
import { PlaygroundPage } from '../pages/PlaygroundPage';
import { SettingsPage } from '../pages/SettingsPage';

const BiPage = lazy(() => import('../features/bi/BiPage'));

export type RouteStatus = 'ready' | 'planned';

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
    path: '/evaluations',
    label: '평가',
    shortLabel: 'Evaluations',
    description: '파이프라인 품질을 비교하는 공간',
    icon: ChartNoAxesCombined,
    component: EvaluationsPage,
    status: 'planned',
  },
  {
    path: '/bi',
    label: 'BI',
    shortLabel: 'BI',
    description: 'BI 기능을 구현하는 독립 작업 공간',
    icon: ChartNoAxesCombined,
    component: BiPage,
    status: 'planned',
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

export function findRoute(pathname: string): AppRoute | undefined {
  return APP_ROUTES.find((route) => route.path === pathname);
}
