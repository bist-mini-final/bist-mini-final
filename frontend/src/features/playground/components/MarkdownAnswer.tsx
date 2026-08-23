import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownAnswerProps {
  markdown: string;
}

export function MarkdownAnswer({ markdown }: MarkdownAnswerProps) {
  return (
    <div className="reader-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
    </div>
  );
}
