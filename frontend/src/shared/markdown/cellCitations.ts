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

export interface StructuredCellEvidence {
  readonly evidence_id: string;
  readonly index_id: string | null;
  readonly workbook_hash: string;
  readonly file_name: string;
  readonly company_name: string | null;
  readonly sheet_name: string;
  readonly cell_coord: string;
  readonly row_header: readonly string[];
  readonly column_header: readonly string[];
  readonly cell_value: string;
  readonly source_text: string;
}

export interface SheetCitationGroup {
  readonly key: string;
  readonly sheet: string;
  readonly citations: readonly CellCitation[];
}

export function citationFromEvidence(evidence: StructuredCellEvidence): CellCitation {
  return {
    sheet: evidence.sheet_name,
    cell: evidence.cell_coord,
    company: evidence.company_name ?? undefined,
    rowHeader: evidence.row_header.join(' > ') || undefined,
    columnHeader: evidence.column_header.join(' > ') || undefined,
    cellValue: evidence.cell_value,
    fileName: evidence.file_name,
    workbookHash: evidence.workbook_hash,
    indexId: evidence.index_id ?? undefined,
    sourceText: evidence.source_text,
  };
}

export function cellCitationLabel(citation: CellCitation): string {
  return citation.label ?? `${citation.sheet.replace(/_/g, ' ')} · ${citation.cell.toUpperCase()}`;
}

function normalizedGroupPart(value: string | undefined): string {
  return value?.trim().toLocaleLowerCase() ?? '';
}

/**
 * Preserve cell-level provenance while presenting one answer badge per source sheet.
 * Workbook identity is part of the key so equally named sheets from different files
 * can never be merged into one verification view.
 */
export function groupCellCitations(citations: readonly CellCitation[]): SheetCitationGroup[] {
  const groups = new Map<string, { sheet: string; citations: CellCitation[]; cells: Set<string> }>();

  citations.forEach((citation) => {
    const key = [
      normalizedGroupPart(citation.indexId),
      normalizedGroupPart(citation.workbookHash),
      normalizedGroupPart(citation.fileName),
      normalizedGroupPart(citation.company),
      normalizedGroupPart(citation.sheet),
    ].join('\u001f');
    const existing = groups.get(key) ?? {
      sheet: citation.sheet,
      citations: [],
      cells: new Set<string>(),
    };
    const cell = citation.cell.trim().toUpperCase();
    if (!existing.cells.has(cell)) {
      existing.cells.add(cell);
      existing.citations.push({ ...citation, cell });
    }
    groups.set(key, existing);
  });

  return [...groups.entries()].map(([key, group]) => ({
    key,
    sheet: group.sheet,
    citations: group.citations,
  }));
}

export function sheetCitationLabel(group: SheetCitationGroup): string {
  return `${group.sheet.replace(/_/g, ' ')} · ${group.citations.length}개 셀`;
}
