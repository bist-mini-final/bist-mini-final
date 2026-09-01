import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { cellEvidenceApi } from '../../../shared/evidence/cellEvidenceApi';
import { CellEvidenceProvider } from '../../../shared/evidence/CellEvidenceProvider';
import type { StructuredCellEvidence } from '../../../shared/markdown/cellCitations';
import { MarkdownAnswer, normalizeMarkdownTables } from './MarkdownAnswer';

vi.mock('../../../shared/evidence/cellEvidenceApi', () => ({
  cellEvidenceApi: {
    resolve: vi.fn(() => new Promise(() => undefined)),
    resolveMany: vi.fn(() => new Promise(() => undefined)),
    imageUrl: vi.fn(() => '/evidence/sheet.png'),
  },
}));

const evidence: StructuredCellEvidence = {
  evidence_id: 'EVIDENCE-001',
  index_id: 'idx-ibm',
  workbook_hash: 'hash-ibm',
  file_name: 'ibm.xlsx',
  company_name: 'IBM',
  sheet_name: 'Income_Statement',
  cell_coord: 'E16',
  row_header: ['Total Revenue'],
  column_header: ['FY2024'],
  cell_value: '62,753',
  source_text: 'Company: IBM | Sheet: Income_Statement | Row Header: Total Revenue | Column Header: FY2024 | Cell Value: 62,753',
};

describe('MarkdownAnswer', () => {
  it('renders emphasis, lists, and GFM tables as semantic HTML', () => {
    const { container } = render(
      <MarkdownAnswer markdown={'**Revenue**\n\n- 62,753\n\n| Year | Value |\n| --- | ---: |\n| 2024 | 62,753 |'} />
    );

    expect(screen.getByText('Revenue').tagName).toBe('STRONG');
    expect(screen.getByText('62,753', { selector: 'li' })).toBeInTheDocument();
    expect(container.querySelector('table')).toBeInTheDocument();
  });

  it('opens the shared evidence dialog from structured cell evidence', () => {
    render(
      <MarkdownAnswer
        markdown="IBM의 2024년 매출은 62,753입니다."
        evidence={[evidence]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Income Statement · 1개 셀' }));

    expect(screen.getByRole('dialog', { name: /시트 원본 근거 검증/ })).toBeInTheDocument();
    expect(cellEvidenceApi.resolveMany).toHaveBeenCalledOnce();
  });

  it('uses the app-level evidence host when rendered inside the provider', async () => {
    render(
      <CellEvidenceProvider>
        <MarkdownAnswer markdown="IBM의 2024년 매출은 62,753입니다." evidence={[evidence]} />
      </CellEvidenceProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Income Statement · 1개 셀' }));

    expect(await screen.findByRole('dialog', { name: /시트 원본 근거 검증/ })).toBeInTheDocument();
  });

  it('groups multiple cell citations from one sheet into one badge', () => {
    render(
      <MarkdownAnswer
        markdown="IBM의 매출과 영업이익입니다."
        evidence={[evidence, { ...evidence, evidence_id: 'EVIDENCE-002', cell_coord: 'F16' }]}
      />,
    );

    expect(screen.getByRole('button', { name: 'Income Statement · 2개 셀' })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });
});

describe('normalizeMarkdownTables', () => {
  it('restores escaped one-line table output before rendering', () => {
    expect(normalizeMarkdownTables(String.raw`\| 항목 | | 2024 | 2025 | |---|---:|---:| | 매출 | 10 | 12 |`)).toBe([
      '| 항목 | 2024 | 2025 |',
      '| --- | ---: | ---: |',
      '| 매출 | 10 | 12 |',
    ].join('\n'));
  });

  it('restores a long financial table with an empty header cell', () => {
    const markdown = String.raw`\| 항목 | | 2014-12-31 | 2015-12-31 | 2016-12-31 | 2017-12-31 | |---|---:|---:|---:|---:| | 영업활동 현금흐름 | 558 | 646 | 750 | 861 |`;

    expect(normalizeMarkdownTables(markdown)).toBe([
      '| 항목 | 2014-12-31 | 2015-12-31 | 2016-12-31 | 2017-12-31 |',
      '| --- | ---: | ---: | ---: | ---: |',
      '| 영업활동 현금흐름 | 558 | 646 | 750 | 861 |',
    ].join('\n'));
  });
});
