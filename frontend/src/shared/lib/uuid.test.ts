import { describe, expect, it } from 'vitest';
import { createUuid } from './uuid';

describe('createUuid', () => {
  it('uses the native implementation when available', () => {
    expect(createUuid({
      randomUUID: () => 'native-uuid',
    })).toBe('native-uuid');
  });

  it('creates a version 4 UUID when randomUUID is unavailable', () => {
    const uuid = createUuid({
      getRandomValues: (values) => {
        values.fill(0);
        return values;
      },
    });

    expect(uuid).toBe('00000000-0000-4000-8000-000000000000');
  });
});
