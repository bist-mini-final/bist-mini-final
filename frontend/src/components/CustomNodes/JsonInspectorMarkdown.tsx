import { Fragment, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { MarkdownInspectorContent } from './jsonInspectorAdapters';

interface JsonInspectorMarkdownProps {
  content: MarkdownInspectorContent;
}

/**
 * Matches cell reference patterns inside square brackets, e.g.:
 *   [Key_Stats Cell A248]
 *   [Sheet1 Cell A1:B10]
 *   [Summary Cell A1:A2, B3]
 */
const CELL_REF_RE = /\[([^\]]+?\s+Cell\s+[A-Z]+\d+(?:[:\s,][A-Z]+\d+)*)\]/gi;

function hasCellRef(text: string): boolean {
  CELL_REF_RE.lastIndex = 0;
  return CELL_REF_RE.test(text);
}

/** Split a text string into alternating plain-text and cell-ref segments. */
function splitCellRefs(text: string): Array<{ type: 'text' | 'ref'; value: string }> {
  const segments: Array<{ type: 'text' | 'ref'; value: string }> = [];
  let lastIndex = 0;
  CELL_REF_RE.lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = CELL_REF_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', value: text.slice(lastIndex, match.index) });
    }
    segments.push({ type: 'ref', value: match[1] });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ type: 'text', value: text.slice(lastIndex) });
  }
  return segments;
}

/**
 * Recursively walk ReactNode children and replace plain string leaves that
 * contain cell references with badge elements. Mixed content (e.g. **bold**
 * next to a ref) is handled correctly because we only touch string nodes.
 */
function injectCellRefBadges(children: ReactNode): ReactNode {
  if (typeof children === 'string') {
    if (!hasCellRef(children)) return children;
    return splitCellRefs(children).map((seg, i) =>
      seg.type === 'ref' ? (
        <span key={i} className="cell-ref" title={`셀 참조: ${seg.value}`}>
          {seg.value}
        </span>
      ) : (
        <Fragment key={i}>{seg.value}</Fragment>
      )
    );
  }
  if (Array.isArray(children)) {
    return children.map((child, i) => {
      const mapped = injectCellRefBadges(child);
      return mapped === child ? child : <Fragment key={i}>{mapped}</Fragment>;
    });
  }
  return children;
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
            // Intercept block-level and inline elements to badge-ify cell refs
            // while keeping all other inline markdown (bold, code, links) intact.
            p: ({ node: _node, children, ...props }) => (
              <p {...props}>{injectCellRefBadges(children)}</p>
            ),
            li: ({ node: _node, children, ...props }) => (
              <li {...props}>{injectCellRefBadges(children)}</li>
            ),
            td: ({ node: _node, children, ...props }) => (
              <td {...props}>{injectCellRefBadges(children)}</td>
            ),
            th: ({ node: _node, children, ...props }) => (
              <th {...props}>{injectCellRefBadges(children)}</th>
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
