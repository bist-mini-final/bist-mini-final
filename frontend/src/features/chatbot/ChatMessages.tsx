import { lazy, Suspense, useEffect, useRef } from 'react';
import { Bot, FileText, RefreshCw } from 'lucide-react';
import { IconButton } from '../../shared/ui';
import type { ChatMessage, PendingChatTurn, ChatProgressStep } from './types';

const DeferredChatAnswer = lazy(() =>
  import('./ChatAnswer').then((module) => ({ default: module.ChatAnswer })),
);
const DeferredChatVisualization = lazy(() =>
  import('./ChatVisualization').then((module) => ({ default: module.ChatVisualization })),
);

interface ChatMessagesProps {
  readonly messages: ChatMessage[];
  readonly progress: ChatProgressStep[];
  readonly pendingTurn: PendingChatTurn | null;
  readonly examples: string[];
  readonly isRunning: boolean;
  readonly isRefreshingSuggestions: boolean;
  readonly requestError: string;
  readonly onAskExample: (example: string) => void;
  readonly onRefreshSuggestions: () => void;
}

const MESSAGE_TIME_FORMATTER = new Intl.DateTimeFormat('ko-KR', {
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const MESSAGE_TIME_TITLE_FORMATTER = new Intl.DateTimeFormat('ko-KR', {
  dateStyle: 'full',
  timeStyle: 'medium',
});

function messageTime(message: ChatMessage): string {
  return message.role === 'assistant' && message.completed_at
    ? message.completed_at
    : message.created_at;
}

function EmptyChat({
  examples,
  isRunning,
  isRefreshingSuggestions,
  requestError,
  onAskExample,
  onRefreshSuggestions,
}: Omit<ChatMessagesProps, 'messages' | 'progress' | 'pendingTurn'>) {
  return (
    <div className="chatbot-empty">
      <Bot size={28} />
      <h2>새 재무 질문을 시작하세요</h2>
      <p>첫 질문을 보내면 내 대화 목록에 저장됩니다.</p>
      <div className="chatbot-examples__heading">
        <span>추천 질문</span>
        <IconButton
          size="sm"
          variant="ghost"
          aria-label="추천 질문 새로고침"
          title="추천 질문 새로고침"
          onClick={onRefreshSuggestions}
          disabled={isRunning || isRefreshingSuggestions}
        >
          <RefreshCw size={15} className={isRefreshingSuggestions ? 'chatbot-spin' : ''} />
        </IconButton>
      </div>
      <div className="chatbot-examples">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onAskExample(example)}
            disabled={isRunning}
          >
            {example}
          </button>
        ))}
      </div>
      {requestError && (
        <small className="chatbot-request-error" role="alert">{requestError}</small>
      )}
    </div>
  );
}

function MessageProgress({ progress }: { readonly progress: ChatProgressStep[] }) {
  return (
    <div className="chatbot-progress">
      {progress.length ? progress.map((step) => (
        <span key={step.id} className={step.state === 'active' ? 'is-active' : ''}>
          {step.state === 'active' && <RefreshCw size={14} className="chatbot-spin" />}
          {step.label}
        </span>
      )) : (
        <span className="is-active">
          <RefreshCw size={14} className="chatbot-spin" />
          답변을 준비하고 있습니다
        </span>
      )}
    </div>
  );
}

function PendingUserMessage({ turn }: { readonly turn: PendingChatTurn }) {
  const parsedTimestamp = new Date(turn.createdAt);
  const validTimestamp = !Number.isNaN(parsedTimestamp.getTime());
  return (
    <article className="chatbot-message chatbot-message--user chatbot-message--pending-user">
      <span className="chatbot-message__avatar">나</span>
      <div className="chatbot-message__body">
        <p>{turn.content}</p>
        {turn.attachmentName && (
          <span className="chatbot-message__attachment">
            <FileText size={13} />
            {turn.attachmentName}
          </span>
        )}
        {validTimestamp && (
          <time
            className="chatbot-message__timestamp"
            dateTime={turn.createdAt}
            title={MESSAGE_TIME_TITLE_FORMATTER.format(parsedTimestamp)}
          >
            {MESSAGE_TIME_FORMATTER.format(parsedTimestamp)}
          </time>
        )}
      </div>
    </article>
  );
}

function PendingAssistantMessage({ progress }: { readonly progress: ChatProgressStep[] }) {
  return (
    <article className="chatbot-message chatbot-message--assistant chatbot-message--pending">
      <span className="chatbot-message__avatar"><Bot size={16} /></span>
      <div className="chatbot-message__body" role="status">
        <MessageProgress progress={progress} />
      </div>
    </article>
  );
}

function ChatMessageItem({
  message,
  progress,
}: {
  readonly message: ChatMessage;
  readonly progress: ChatProgressStep[];
}) {
  const timestamp = messageTime(message);
  const parsedTimestamp = new Date(timestamp);
  const validTimestamp = !Number.isNaN(parsedTimestamp.getTime());
  return (
    <article className={`chatbot-message chatbot-message--${message.role}`}>
      <span className="chatbot-message__avatar">
        {message.role === 'assistant' ? <Bot size={16} /> : '나'}
      </span>
      <div className="chatbot-message__body">
        {message.status === 'processing' ? (
          <MessageProgress progress={progress} />
        ) : message.role === 'assistant' ? (
          <Suspense fallback={<span className="chatbot-content-loading">답변 표시 준비 중...</span>}>
            <DeferredChatAnswer markdown={message.content} evidence={message.evidence} />
          </Suspense>
        ) : (
          <>
            <p>{message.content}</p>
            {message.attachments.map((attachment) => (
              <span key={attachment.id} className="chatbot-message__attachment">
                <FileText size={13} />
                {attachment.name}
              </span>
            ))}
          </>
        )}
        {message.visualization && message.status === 'completed' && (
          <Suspense fallback={(
            <div className="chatbot-visualization chatbot-visualization--loading">
              차트를 불러오는 중...
            </div>
          )}>
            <DeferredChatVisualization visualization={message.visualization} />
          </Suspense>
        )}
        {message.status === 'failed' && <small>답변 생성에 실패했습니다.</small>}
        {validTimestamp && (
          <time
            className="chatbot-message__timestamp"
            dateTime={timestamp}
            title={MESSAGE_TIME_TITLE_FORMATTER.format(parsedTimestamp)}
          >
            {MESSAGE_TIME_FORMATTER.format(parsedTimestamp)}
          </time>
        )}
      </div>
    </article>
  );
}

export function ChatMessages(props: ChatMessagesProps) {
  const { messages, pendingTurn, progress } = props;
  const endRef = useRef<HTMLDivElement>(null);
  const lastMessage = messages[messages.length - 1];
  const showPendingAssistant = props.isRunning
    && (pendingTurn !== null || lastMessage?.role !== 'assistant');

  useEffect(() => {
    if (!props.isRunning) return;
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' });
  }, [messages.length, pendingTurn, props.isRunning]);

  return (
    <div className="chatbot-messages" aria-live="polite" aria-busy={props.isRunning}>
      {messages.length === 0 && !pendingTurn && <EmptyChat {...props} />}
      {messages.map((message) => (
        <ChatMessageItem key={message.id} message={message} progress={progress} />
      ))}
      {pendingTurn && <PendingUserMessage turn={pendingTurn} />}
      {showPendingAssistant && <PendingAssistantMessage progress={progress} />}
      <div ref={endRef} className="chatbot-messages__anchor" aria-hidden="true" />
    </div>
  );
}
