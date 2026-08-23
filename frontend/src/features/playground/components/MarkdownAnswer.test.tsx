import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MarkdownAnswer } from './MarkdownAnswer';

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
