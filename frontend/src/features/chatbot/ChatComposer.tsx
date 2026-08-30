import { type FormEvent, useRef } from 'react';
import { CircleStop, FileText, Paperclip, Send, X } from 'lucide-react';
import { Button, IconButton } from '../../shared/ui';

interface ChatComposerProps {
  readonly draft: string;
  readonly attachment: File | null;
  readonly isRunning: boolean;
  readonly onDraftChange: (value: string) => void;
  readonly onAttachmentChange: (file: File | null) => void;
  readonly onAsk: () => void;
  readonly onStop: () => void;
}

export function ChatComposer({
  draft,
  attachment,
  isRunning,
  onDraftChange,
  onAttachmentChange,
  onAsk,
  onStop,
}: ChatComposerProps) {
  const attachmentInput = useRef<HTMLInputElement>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onAsk();
  };

  return (
    <form className="chatbot-composer" onSubmit={submit}>
      {attachment && (
        <div className="chatbot-attachment">
          <FileText size={14} />
          <span>{attachment.name}</span>
          <IconButton
            size="sm"
            variant="ghost"
            aria-label="첨부 파일 제거"
            onClick={() => onAttachmentChange(null)}
          >
            <X size={13} />
          </IconButton>
        </div>
      )}
      <textarea
        value={draft}
        onChange={(event) => onDraftChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            onAsk();
          }
        }}
        placeholder="예: IBM의 2025년 총자산은 얼마인가요?"
        rows={2}
        disabled={isRunning}
      />
      <div className="chatbot-composer__actions">
        <input
          ref={attachmentInput}
          type="file"
          accept=".txt,.md,.csv,.json,.xlsx,.xlsm"
          hidden
          onChange={(event) => {
            onAttachmentChange(event.target.files?.[0] ?? null);
            event.target.value = '';
          }}
        />
        <IconButton
          size="sm"
          variant="secondary"
          className="chatbot-attach"
          aria-label="파일 첨부"
          title="파일 첨부"
          onClick={() => attachmentInput.current?.click()}
          disabled={isRunning}
        >
          <Paperclip size={17} />
        </IconButton>
        {isRunning ? (
          <Button size="sm" variant="danger-solid" className="chatbot-stop" onClick={onStop}>
            <CircleStop size={16} /> 중지
          </Button>
        ) : (
          <Button size="sm" variant="primary" type="submit" disabled={!draft.trim()}>
            <Send size={16} /> 질문하기
          </Button>
        )}
      </div>
    </form>
  );
}
