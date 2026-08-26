import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MarkdownAnswer, normalizeMarkdownTables } from './MarkdownAnswer';

describe('MarkdownAnswer', () => {
  it('renders emphasis, lists, and GFM tables as semantic HTML', () => {
    const { container } = render(
      <MarkdownAnswer markdown={'**Revenue**\n\n- 62,753\n\n| Year | Value |\n| --- | ---: |\n| 2024 | 62,753 |'} />
    );

    expect(screen.getByText('Revenue').tagName).toBe('STRONG');
    expect(screen.getByText('62,753', { selector: 'li' })).toBeInTheDocument();
    expect(container.querySelector('table')).toBeInTheDocument();
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
});
