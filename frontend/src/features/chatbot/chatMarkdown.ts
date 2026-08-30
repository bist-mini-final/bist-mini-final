import { normalizeCellCitations } from '../../shared/markdown/cellCitations';

function repairInlineTable(markdown: string) {
  const normalized = markdown.replace(/\\+\|/g, '|');
  return normalized.split('\n').map((line) => repairInlineTableLine(line)).join('\n');
}

function repairInlineTableLine(line: string) {
  if (!line.includes('|---')) return line;

  const separatorStart = line.indexOf('|---');
  const tableStart = line.indexOf('|');
  if (tableStart < 0 || tableStart >= separatorStart) return line;
  const headerCells = line.slice(tableStart, separatorStart).split('|').map((cell) => cell.trim()).filter(Boolean);
  const cellsAfterHeader = line.slice(separatorStart).split('|').map((cell) => cell.trim()).filter(Boolean);
  if (headerCells.length < 3 || cellsAfterHeader.length < headerCells.length) return line;

  const separatorCells = cellsAfterHeader.slice(0, headerCells.length);
  if (!separatorCells.every((cell) => /^:?-{3,}:?$/.test(cell))) return line;
  const dataCells = cellsAfterHeader.slice(headerCells.length);
  const rowCount = Math.floor(dataCells.length / headerCells.length);
  if (!rowCount) return line;

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
}

function repairCollapsedDateTableHeaders(markdown: string) {
  const lines = markdown.split('\n');
  return lines.map((line, index) => {
    const separator = lines[index + 1] ?? '';
    if (!line.trimStart().startsWith('|') || !separator.trimStart().startsWith('|')) return line;

    const dates = line.match(/20\d{2}-\d{2}-\d{2}/g) ?? [];
    const separatorCells = separator.split('|').filter((cell) => cell.trim());
    const headerCells = line.split('|').map((cell) => cell.trim()).filter(Boolean);
    if (dates.length < 2 || separatorCells.length !== dates.length + 1 || headerCells.length === separatorCells.length) return line;

    const title = headerCells[0];
    if (!title) return line;
    return `| ${[title, ...dates].join(' | ')} |`;
  }).join('\n');
}

export function normalizeChatMarkdown(markdown: string) {
  const normalized = repairCollapsedDateTableHeaders(repairInlineTable(markdown))
    .replace(/(?<![A-Za-z])NA(?![A-Za-z])\s*로?\s*근거가 부족(?:합니다|해요)?/gi, '확인 가능한 근거가 부족해 요약에서 제외했습니다')
    .replace(/(?<![A-Za-z])NA(?![A-Za-z])\s*로 표시되어 있어/gi, '확인 가능한 값이 없어')
    .replace(/\s*[;；]\s*(?=(?:\*\*)?[^\n]*확인 가능한 근거가 부족)/g, '\n\n')
    .replace(/(\d{4})~~(\d{4})/g, '$1–$2')
    .replace(/\\([*_`[\].~])/g, '$1')
    .replace(/(\*\*[^*\n]+?\*\*)(?=[가-힣])/g, '$1 ');
  return normalizeCellCitations(normalized);
}
