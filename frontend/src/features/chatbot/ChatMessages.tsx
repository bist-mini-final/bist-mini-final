import { lazy, Suspense } from 'react';
import { Bot, FileText, RefreshCw } from 'lucide-react';
import { IconButton } from '../../shared/ui';
import type { ChatMessage, ChatProgressStep } from './types';

const DeferredChatAnswer = lazy(() =>
  import('./ChatAnswer').then((module) => ({ default: module.ChatAnswer })),
);
const DeferredChatVisualization = lazy(() =>
  import('./ChatVisualization').then((module) => ({ default: module.ChatVisualization })),
);

interface ChatMessagesProps {
  readonly messages: ChatMessage[];
  readonly progress: ChatProgressStep[];
  readonly examples: string[];
  readonly isRunning: boolean;
  readonly isRefreshingSuggestions: boolean;
  readonly requestError: string;
  readonly onAskExample: (example: string) => void;
  readonly onRefreshSuggestions: () => void;
}

function EmptyChat({
  examples,
  isRunning,
  isRefreshingSuggestions,
  requestError,
  onAskExample,
  onRefreshSuggestions,
}: Omit<ChatMessagesProps, 'messages' | 'progress'>) {
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

function ChatMessageItem({
  message,
  progress,
}: {
  readonly message: ChatMessage;
  readonly progress: ChatProgressStep[];
}) {
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
            <DeferredChatAnswer markdown={message.content} />
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
      </div>
    </article>
  );
}

export function ChatMessages(props: ChatMessagesProps) {
  const { messages, progress } = props;
  return (
    <div className="chatbot-messages" aria-live="polite" aria-busy={props.isRunning}>
      {messages.length === 0 && <EmptyChat {...props} />}
      {messages.map((message) => (
        <ChatMessageItem key={message.id} message={message} progress={progress} />
      ))}
    </div>
  );
}
