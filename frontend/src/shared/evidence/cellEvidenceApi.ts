import { requestJson, versionedApiEndpoint } from '../api/httpClient';
import type { CellCitation } from '../markdown/cellCitations';

export interface CellEvidenceImage {
  readonly rendered_available: boolean;
  readonly typed_available: boolean;
  readonly image_width: number | null;
  readonly image_height: number | null;
  readonly cell_bbox_px: readonly [number, number, number, number] | null;
  readonly unavailable_reason: string | null;
}

export interface CellEvidence {
  readonly company_name: string;
  readonly index_id: string;
  readonly file_name: string;
  readonly workbook_hash: string;
  readonly sheet_name: string;
  readonly cell_coord: string;
  readonly cell_value: string | null;
  readonly row_header: readonly string[];
  readonly column_header: readonly string[];
  readonly source_text: string;
  readonly image: CellEvidenceImage;
}

export const cellEvidenceApi = {
  resolve(citation: CellCitation, signal?: AbortSignal) {
    const query = new URLSearchParams({
      sheet_name: citation.sheet,
      cell_coord: citation.cell,
    });
    if (citation.company) query.set('company_name', citation.company);
    if (citation.workbookHash) query.set('workbook_hash', citation.workbookHash);
    if (citation.cellValue) query.set('cell_value', citation.cellValue);
    return requestJson<CellEvidence>(`/api/evidence/cells/resolve?${query}`, { signal });
  },

  imageUrl(evidence: CellEvidence) {
    return versionedApiEndpoint(
      `/api/spreadsheet-artifacts/${encodeURIComponent(evidence.workbook_hash)}`
      + `/sheets/${encodeURIComponent(evidence.sheet_name)}?layer=rendered`,
    );
  },
};
