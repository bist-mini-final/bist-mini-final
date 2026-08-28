import { render } from '@testing-library/react';
import { screen } from '@testing-library/react';
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

  it('renders verified cell evidence as a citation chip', () => {
    const markdown = normalizeChatMarkdown('**근거**\n- [Sheet: Balance Sheet | Cell: E50] IBM 총자산: 151,880');

    const { container } = render(<MarkdownAnswer markdown={markdown} />);

    expect(container.querySelector('.chatbot-citation-chip')).toHaveTextContent('Balance Sheet · E50');
  });
});
