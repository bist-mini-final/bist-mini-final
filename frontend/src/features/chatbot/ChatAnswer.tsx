import { MarkdownAnswer } from '../playground/components/MarkdownAnswer';
import { normalizeChatMarkdown } from './chatMarkdown';

interface ChatAnswerProps {
  readonly markdown: string;
}

/** Heavy Markdown renderer loaded only when an assistant answer is visible. */
export function ChatAnswer({ markdown }: ChatAnswerProps) {
  return <MarkdownAnswer markdown={normalizeChatMarkdown(markdown)} />;
}
