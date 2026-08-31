import { Pencil, Trash2 } from 'lucide-react';
import { IconButton } from '../../shared/ui';
import type { ChatSession } from './types';

interface ChatSessionSidebarProps {
  readonly sessions: ChatSession[];
  readonly activeSessionId?: string;
  readonly disabled: boolean;
  readonly onSelectSession: (sessionId: string) => void;
  readonly onRenameSession: (session: ChatSession) => void;
  readonly onDeleteSession: (session: ChatSession) => void;
}

function formatDate(date: string): string {
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(date));
}

export function ChatSessionSidebar({
  sessions,
  activeSessionId,
  disabled,
  onSelectSession,
  onRenameSession,
  onDeleteSession,
}: ChatSessionSidebarProps) {
  return (
    <section className="chatbot-sessions" aria-label="대화 이력">
      <span className="chatbot-sessions__label">대화 이력</span>
      {sessions.length === 0 && (
        <p className="chatbot-sessions__empty">저장된 대화가 없습니다.</p>
      )}
      {sessions.map((session) => (
        <div
          key={session.id}
          className={`chatbot-session${activeSessionId === session.id ? ' is-active' : ''}`}
          title={`최근 대화: ${formatDate(session.updated_at)}`}
        >
          <button
            type="button"
            className="chatbot-session__select"
            onClick={() => onSelectSession(session.id)}
            disabled={disabled}
          >
            <strong>{session.title}</strong>
          </button>
          <span className="chatbot-session__actions">
            <IconButton
              size="sm"
              variant="ghost"
              aria-label={`${session.title} 제목 편집`}
              onClick={() => onRenameSession(session)}
              disabled={disabled}
            >
              <Pencil size={13} />
            </IconButton>
            <IconButton
              size="sm"
              variant="ghost"
              aria-label={`${session.title} 삭제`}
              onClick={() => onDeleteSession(session)}
              disabled={disabled}
            >
              <Trash2 size={13} />
            </IconButton>
          </span>
        </div>
      ))}
    </section>
  );
}
