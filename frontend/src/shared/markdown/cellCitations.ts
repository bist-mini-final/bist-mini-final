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
