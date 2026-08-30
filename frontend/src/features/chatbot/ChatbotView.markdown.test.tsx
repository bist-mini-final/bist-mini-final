import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MarkdownAnswer } from '../playground/components/MarkdownAnswer';
import { normalizeChatMarkdown } from './chatMarkdown';

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

  it('collapses verbose cell evidence into a citation chip with hover details', () => {
    const markdown = normalizeChatMarkdown([
      '**근거**',
      '- [Sheet: Balance_Sheet | Cell: E50] Company: IBM | Sheet: Balance_Sheet | Row Header: Total Assets | Column Header: 2024-12-31 | Cell Value: 151,880',
    ].join('\n'));

    const { container } = render(<MarkdownAnswer markdown={markdown} />);
    const chip = container.querySelector('.reader-citation');

    expect(chip).toHaveTextContent('Balance Sheet · E50');
    expect(container).not.toHaveTextContent('Row Header: Total Assets');

    fireEvent.mouseEnter(chip!);
    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toHaveTextContent('IBM');
    expect(tooltip).toHaveTextContent('Total Assets');
    expect(tooltip).toHaveTextContent('2024-12-31');
    expect(tooltip).toHaveTextContent('151,880');
  });
});
