import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownAnswer } from '../playground/components/MarkdownAnswer';
import type { StructuredCellEvidence } from '../../shared/markdown/cellCitations';
import { normalizeChatMarkdown } from './chatMarkdown';

const evidenceApiMock = vi.hoisted(() => ({
  resolve: vi.fn(() => new Promise(() => undefined)),
  imageUrl: vi.fn(() => '/evidence.png'),
}));

vi.mock('../../shared/evidence/cellEvidenceApi', () => ({
  cellEvidenceApi: evidenceApiMock,
}));

const evidence: StructuredCellEvidence = {
  evidence_id: 'EVIDENCE-001',
  index_id: 'idx-ibm',
  workbook_hash: 'hash-ibm',
  file_name: 'ibm.xlsx',
  company_name: 'IBM',
  sheet_name: 'Balance_Sheet',
  cell_coord: 'E50',
  row_header: ['Total Assets'],
  column_header: ['2024-12-31'],
  cell_value: '151,880',
  source_text: 'Company: IBM | Sheet: Balance_Sheet | Row Header: Total Assets | Column Header: 2024-12-31 | Cell Value: 151,880',
};

describe('normalizeChatMarkdown', () => {
  it('preserves an already valid financial table header', () => {
    const markdown = [
      '현금흐름 추이는 다음과 같습니다.',
      '',
      '| 항목 | 2014-12-31 | 2015-12-31 |',
      '|---|---:|---:|',
      '| 영업활동 현금흐름 | 558 | 646 |',
    ].join('\n');

    const normalized = normalizeChatMarkdown(markdown);

    expect(normalized).toContain('| 항목 | 2014-12-31 | 2015-12-31 |');
    expect(normalized).not.toContain('| 항목 | | 2014-12-31');
    expect(render(<MarkdownAnswer markdown={normalized} />).container.querySelector('table')).toBeInTheDocument();
  });

  it('renders escaped and unescaped percentage emphasis as bold text', () => {
    const markdown = normalizeChatMarkdown('성장률은 **10.6%, 11.0%, 11.1%**이며, \\*\\*38.0%에서 48.0%\\*\\*로 확대됐습니다.');

    render(<MarkdownAnswer markdown={markdown} />);

    expect(screen.getByText('10.6%, 11.0%, 11.1%').tagName).toBe('STRONG');
    expect(screen.getByText('38.0%에서 48.0%').tagName).toBe('STRONG');
  });

  it('renders structured evidence as a citation chip with hover details', () => {
    const markdown = normalizeChatMarkdown('IBM의 총자산은 151,880입니다.');

    const { container } = render(<MarkdownAnswer markdown={markdown} evidence={[evidence]} />);
    const chip = container.querySelector('.reader-citation');

    expect(chip).toHaveTextContent('Balance Sheet · E50');
    expect(container).not.toHaveTextContent('Row Header: Total Assets');

    fireEvent.mouseEnter(chip!);
    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toHaveTextContent('IBM');
    expect(tooltip).toHaveTextContent('Total Assets');
    expect(tooltip).toHaveTextContent('2024-12-31');
    expect(tooltip).toHaveTextContent('151,880');

    fireEvent.click(chip!);
    expect(screen.getByRole('dialog', { name: '셀 원본 근거 검증' })).toBeInTheDocument();
    expect(evidenceApiMock.resolve).toHaveBeenCalledWith(
      expect.objectContaining({ company: 'IBM', sheet: 'Balance_Sheet', cell: 'E50' }),
      expect.any(AbortSignal),
    );
  });
});
