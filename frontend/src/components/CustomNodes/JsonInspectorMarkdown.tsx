import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { MarkdownInspectorContent } from './jsonInspectorAdapters';

interface JsonInspectorMarkdownProps {
  content: MarkdownInspectorContent;
}

export default function JsonInspectorMarkdown({ content }: JsonInspectorMarkdownProps) {
  return (
    <div className="json-inspector-answer nodrag nopan">
      <div className="json-inspector-answer__heading">
        <span>{content.label}</span>
        <small>Markdown</small>
      </div>
      <div className="json-inspector-markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ node: _node, ...props }) => (
              <a {...props} target="_blank" rel="noreferrer" />
            ),
          }}
        >
          {content.markdown}
        </ReactMarkdown>
      </div>
      {content.truncated && (
        <p className="json-inspector-answer__truncated">
          저장된 실행 이력 미리보기입니다
          {content.sourceCharacters ? ` · 원문 ${content.sourceCharacters}자` : ''}.
        </p>
      )}
    </div>
  );
}
