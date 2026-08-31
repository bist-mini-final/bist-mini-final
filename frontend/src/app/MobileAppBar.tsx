import { Bell, Menu } from 'lucide-react';
import type { RefObject } from 'react';
import { IconButton } from '../shared/ui';
import type { AppRoute } from './routes';

interface MobileAppBarProps {
  readonly activeRoute?: AppRoute;
  readonly menuButtonRef: RefObject<HTMLButtonElement>;
  readonly notificationOpen: boolean;
  readonly onOpenMenu: () => void;
  readonly onToggleNotification: () => void;
}

export function MobileAppBar({
  activeRoute,
  menuButtonRef,
  notificationOpen,
  onOpenMenu,
  onToggleNotification,
}: MobileAppBarProps) {
  return (
    <header className="mobile-app-bar">
      <IconButton
        ref={menuButtonRef}
        variant="ghost"
        type="button"
        onClick={onOpenMenu}
        aria-label="전체 메뉴 열기"
        aria-controls="product-sidebar"
      >
        <Menu size={20} aria-hidden="true" />
      </IconButton>
      <div className="mobile-app-bar__title">
        <strong>Excel RAG</strong>
        <span>{activeRoute?.label ?? 'Workspace'}</span>
      </div>
      <IconButton
        variant="ghost"
        type="button"
        onClick={onToggleNotification}
        aria-label="알림"
        aria-expanded={notificationOpen}
      >
        <Bell size={18} aria-hidden="true" />
      </IconButton>
      {notificationOpen ? (
        <div className="mobile-app-bar__notification" role="status">
          <strong>알림</strong>
          <span>새 알림이 없습니다.</span>
        </div>
      ) : null}
    </header>
  );
}
