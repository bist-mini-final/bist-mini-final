import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { cellEvidenceApi } from '../../../shared/evidence/cellEvidenceApi';
import { CellEvidenceProvider } from '../../../shared/evidence/CellEvidenceProvider';
import { MarkdownAnswer, normalizeMarkdownTables } from './MarkdownAnswer';

vi.mock('../../../shared/evidence/cellEvidenceApi', () => ({
  cellEvidenceApi: {
    resolve: vi.fn(() => new Promise(() => undefined)),
    imageUrl: vi.fn(() => '/evidence/sheet.png'),
  },
}));

describe('MarkdownAnswer', () => {
  it('renders emphasis, lists, and GFM tables as semantic HTML', () => {
    const { container } = render(
      <MarkdownAnswer markdown={'**Revenue**\n\n- 62,753\n\n| Year | Value |\n| --- | ---: |\n| 2024 | 62,753 |'} />
    );

    expect(screen.getByText('Revenue').tagName).toBe('STRONG');
    expect(screen.getByText('62,753', { selector: 'li' })).toBeInTheDocument();
    expect(container.querySelector('table')).toBeInTheDocument();
  });

  it('opens the shared evidence dialog from a parsed cell citation chip', () => {
    render(
      <MarkdownAnswer
        markdown="근거: [Sheet: Income_Statement | Cell: E16]"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Income Statement · E16' }));

    expect(screen.getByRole('dialog', { name: /셀 원본 근거 검증/ })).toBeInTheDocument();
    expect(cellEvidenceApi.resolve).toHaveBeenCalledOnce();
  });

  it('uses the app-level evidence host when rendered inside the provider', async () => {
    render(
      <CellEvidenceProvider>
        <MarkdownAnswer markdown="근거: [Sheet: Income_Statement | Cell: E16]" />
      </CellEvidenceProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Income Statement · E16' }));

    expect(await screen.findByRole('dialog', { name: /셀 원본 근거 검증/ })).toBeInTheDocument();
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
