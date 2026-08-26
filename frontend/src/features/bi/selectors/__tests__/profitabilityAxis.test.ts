import { describe, expect, it } from 'vitest';
import { buildProfitabilityAxis } from '../chartViewModel';

describe('buildProfitabilityAxis', () => {
  it('keeps a negative final margin and its label above the x-axis', () => {
    // Given
    const margins = [12.1, 9.6, -3];

    // When
    const axis = buildProfitabilityAxis(margins);

    // Then
    expect(axis.domain).toEqual([-10, 20]);
    expect(axis.ticks).toEqual([-10, -5, 0, 5, 10, 15, 20]);
  });
});
