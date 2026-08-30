import { describe, expect, it } from 'vitest';
import {
  normalizeCellCitations,
  parseCellCitationHref,
} from './cellCitations';

describe('cell citation markdown', () => {
  it('removes structured source details from the visible markdown and keeps them in metadata', () => {
    const normalized = normalizeCellCitations(
      '- [Sheet: Balance_Sheet | Cell: P74] Company: DHIN | Sheet: Balance_Sheet | Row Header: Total Liabilities | Column Header: 2025-12-31 | Cell Value: 9,015',
    );
    const href = /\((https:\/\/citation\.local\/[^)]+)\)/.exec(normalized)?.[1];
    const citation = parseCellCitationHref(href);

    expect(normalized).toMatch(/^- \[Balance Sheet · P74\]/);
    expect(normalized).not.toContain('Row Header:');
    expect(citation).toMatchObject({
      company: 'DHIN',
      sheet: 'Balance_Sheet',
      cell: 'P74',
      rowHeader: 'Total Liabilities',
      columnHeader: '2025-12-31',
      cellValue: '9,015',
    });
  });

  it('keeps ordinary text after an inline cell citation', () => {
    const normalized = normalizeCellCitations(
      '총자산은 10,081입니다. [Sheet: Balance_Sheet | Cell: O50] 이 값은 최신 기준입니다.',
    );

    expect(normalized).toContain('이 값은 최신 기준입니다.');
  });
});
