import { MarkdownAnswer } from '../playground/components/MarkdownAnswer';
import { normalizeChatMarkdown } from './chatMarkdown';
import type { StructuredCellEvidence } from '../../shared/markdown/cellCitations';

interface ChatAnswerProps {
  readonly markdown: string;
  readonly evidence: readonly StructuredCellEvidence[];
}

/** Heavy Markdown renderer loaded only when an assistant answer is visible. */
export function ChatAnswer({ markdown, evidence }: ChatAnswerProps) {
  return <MarkdownAnswer markdown={normalizeChatMarkdown(markdown)} evidence={evidence} />;
}
