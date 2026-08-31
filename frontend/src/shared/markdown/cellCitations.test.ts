import { describe, expect, it } from 'vitest';
import { citationFromEvidence } from './cellCitations';

describe('structured cell evidence projection', () => {
  it('maps the backend evidence DTO to the evidence viewer citation contract', () => {
    const citation = citationFromEvidence({
      evidence_id: 'EVIDENCE-001',
      index_id: 'idx_dhin',
      workbook_hash: 'abc123',
      file_name: 'dhin.xlsx',
      company_name: 'DHIN',
      sheet_name: 'Balance_Sheet',
      cell_coord: 'P74',
      row_header: ['Total Liabilities'],
      column_header: ['2025-12-31'],
      cell_value: '9,015',
      source_text: 'Company: DHIN | Sheet: Balance_Sheet | Cell Value: 9,015',
    });

    expect(citation).toEqual({
      company: 'DHIN',
      sheet: 'Balance_Sheet',
      cell: 'P74',
      rowHeader: 'Total Liabilities',
      columnHeader: '2025-12-31',
      cellValue: '9,015',
      fileName: 'dhin.xlsx',
      workbookHash: 'abc123',
      indexId: 'idx_dhin',
      sourceText: 'Company: DHIN | Sheet: Balance_Sheet | Cell Value: 9,015',
    });
  });
});
