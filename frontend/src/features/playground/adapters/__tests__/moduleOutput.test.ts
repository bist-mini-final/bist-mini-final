import { describe, expect, it } from 'vitest';
import { unwrapModuleOutput } from '../moduleOutput';

describe('module output adapter', () => {
  it('unwraps a named output port', () => {
    expect(unwrapModuleOutput({ answer_json: { answer: '62,753' } }, 'answer_json'))
      .toEqual({ answer: '62,753' });
  });

  it('accepts a legacy direct output payload', () => {
    expect(unwrapModuleOutput({ answer: '62,753' }, 'answer_json'))
      .toEqual({ answer: '62,753' });
  });

  it('rejects non-object payloads', () => {
    expect(unwrapModuleOutput(null, 'answer_json')).toBeNull();
  });
});
