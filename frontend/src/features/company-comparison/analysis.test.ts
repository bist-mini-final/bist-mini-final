import { describe, expect, it } from 'vitest';
import { formatCompositeScore } from './analysis';

describe('formatCompositeScore', () => {
  it('preserves the precision used to distinguish official ranking scores', () => {
    expect(formatCompositeScore(93.03)).toBe('93.03');
    expect(formatCompositeScore(93.02)).toBe('93.02');
  });
});
