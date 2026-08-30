export const CELL_CITATION_URL_PREFIX = 'https://citation.local/';

export interface CellCitation {
  readonly sheet: string;
  readonly cell: string;
  readonly label?: string;
  readonly company?: string;
  readonly rowHeader?: string;
  readonly columnHeader?: string;
  readonly cellValue?: string;
  readonly fileName?: string;
  readonly workbookHash?: string;
  readonly indexId?: string;
  readonly sourceText?: string;
}

const CELL_REFERENCE = /\[Sheet:\s*([^\]|]+?)\s*\|\s*Cell:\s*([A-Za-z]{1,3}\d+)\](?!\()/gi;
const STRUCTURED_FIELD = /(?:^|\|)\s*(Company|Sheet|Row Header|Column Header|Cell Value|File Name|Workbook Hash|Index ID):\s*([^|]*)/gi;

function clean(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized || undefined;
}

function structuredFields(sourceText: string): Partial<CellCitation> {
  const values: Record<string, string> = {};
  for (const match of sourceText.matchAll(STRUCTURED_FIELD)) {
    values[match[1].toLowerCase()] = match[2].trim();
  }
  return {
    company: clean(values.company),
    sheet: clean(values.sheet),
    rowHeader: clean(values['row header']),
    columnHeader: clean(values['column header']),
    cellValue: clean(values['cell value']),
    fileName: clean(values['file name']),
    workbookHash: clean(values['workbook hash']),
    indexId: clean(values['index id']),
  };
}

export function cellCitationLabel(citation: CellCitation): string {
  return citation.label ?? `${citation.sheet.replace(/_/g, ' ')} · ${citation.cell.toUpperCase()}`;
}

export function cellCitationHref(citation: CellCitation): string {
  return `${CELL_CITATION_URL_PREFIX}${encodeURIComponent(JSON.stringify(citation))}`;
}

export function parseCellCitationHref(href: string | undefined): CellCitation | null {
  if (!href?.startsWith(CELL_CITATION_URL_PREFIX)) return null;
  try {
    const decoded = JSON.parse(decodeURIComponent(href.slice(CELL_CITATION_URL_PREFIX.length))) as CellCitation;
    return decoded && typeof decoded.sheet === 'string' && typeof decoded.cell === 'string'
      ? decoded
      : null;
  } catch {
    const legacyLabel = decodeURIComponent(href.slice(CELL_CITATION_URL_PREFIX.length));
    const [sheet = '출처', cell = '셀'] = legacyLabel.split('·').map((part) => part.trim());
    return { sheet, cell, label: legacyLabel };
  }
}

function citationLink(citation: CellCitation): string {
  return `[${cellCitationLabel(citation)}](${cellCitationHref(citation)})`;
}

function replaceCellReferences(line: string): string {
  const firstReference = new RegExp(CELL_REFERENCE.source, 'i').exec(line);
  if (!firstReference) return line;

  const trailingText = line.slice(firstReference.index + firstReference[0].length).trim();
  const details = structuredFields(trailingText);
  const hasStructuredDetails = Boolean(
    details.company || details.sheet || details.rowHeader || details.columnHeader || details.cellValue
      || details.fileName || details.workbookHash || details.indexId,
  );

  if (hasStructuredDetails) {
    const citation: CellCitation = {
      sheet: details.sheet ?? firstReference[1].trim(),
      cell: firstReference[2].toUpperCase(),
      company: details.company,
      rowHeader: details.rowHeader,
      columnHeader: details.columnHeader,
      cellValue: details.cellValue,
      fileName: details.fileName,
      workbookHash: details.workbookHash,
      indexId: details.indexId,
      sourceText: trailingText,
    };
    return `${line.slice(0, firstReference.index)}${citationLink(citation)}`.trimEnd();
  }

  return line.replace(CELL_REFERENCE, (_match, sheet: string, cell: string) => citationLink({
    sheet: sheet.trim(),
    cell: cell.toUpperCase(),
  }));
}

function replaceLegacyReferences(line: string): string {
  return line.replace(/\[([^\]]+:[^\]]+)\](?!\()/g, (_match, source: string) => {
    const [sheet, detail = ''] = source.split(':', 2);
    const [field, period] = detail.split('|').map((item) => item.trim());
    const label = `${sheet.replace(/_/g, ' ')}${field ? ` · ${field}` : ''}${period ? ` · ${period}` : ''}`;
    return citationLink({ sheet: sheet.trim(), cell: period || field || '출처', label });
  });
}

export function normalizeCellCitations(markdown: string): string {
  return markdown
    .split('\n')
    .map((line) => replaceLegacyReferences(replaceCellReferences(line)))
    .join('\n');
}
