import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownAnswerProps {
  markdown: string;
}

export function normalizeMarkdownTables(markdown: string) {
  return markdown.replace(/\\+\|/g, '|').split('\n').map((line) => {
    const separatorStart = line.indexOf('|---');
    const tableStart = line.indexOf('|');
    if (separatorStart < 0 || tableStart < 0 || tableStart >= separatorStart) return line;

    const headerCells = line.slice(tableStart, separatorStart).split('|').map((cell) => cell.trim()).filter(Boolean);
    const remainingCells = line.slice(separatorStart).split('|').map((cell) => cell.trim()).filter(Boolean);
    const separatorCells = remainingCells.slice(0, headerCells.length);
    const dataCells = remainingCells.slice(headerCells.length);
    const rowCount = Math.floor(dataCells.length / headerCells.length);
    if (headerCells.length < 3 || !rowCount || !separatorCells.every((cell) => /^:?-{3,}:?$/.test(cell))) return line;

    const rows = Array.from({ length: rowCount }, (_, row) =>
      dataCells.slice(row * headerCells.length, (row + 1) * headerCells.length),
    );
    const table = [
      `| ${headerCells.join(' | ')} |`,
      `| ${separatorCells.join(' | ')} |`,
      ...rows.map((row) => `| ${row.join(' | ')} |`),
    ].join('\n');
    const remainder = dataCells.slice(rowCount * headerCells.length).join(' | ').trim();
    return `${line.slice(0, tableStart)}${table}${remainder ? `\n${remainder}` : ''}`;
  }).join('\n');
}

export function MarkdownAnswer({ markdown }: MarkdownAnswerProps) {
  return (
    <div className="reader-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => href?.startsWith('https://citation.local/')
            ? <span className="chatbot-citation-chip">{children}</span>
            : <a href={href}>{children}</a>,
        }}
      >
        {normalizeMarkdownTables(markdown)}
      </ReactMarkdown>
    </div>
  );
}
