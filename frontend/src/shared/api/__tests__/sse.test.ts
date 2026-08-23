import { describe, expect, it } from 'vitest';
import { SseDecoder } from '../sse';

describe('SseDecoder', () => {
  it('emits CRLF-delimited events before the stream closes', () => {
    const decoder = new SseDecoder();

    expect(decoder.push('event: node_progress\r\ndata: {"node_id":"query",'))
      .toEqual([]);
    expect(decoder.push('"status":"running"}\r\n\r\n'))
      .toEqual([{
        event: 'node_progress',
        data: '{"node_id":"query","status":"running"}',
      }]);
  });

  it('supports LF frames, comments, and multiline data', () => {
    const decoder = new SseDecoder();
    expect(decoder.push(': keep-alive\nevent: update\ndata: first\ndata: second\n\n'))
      .toEqual([{ event: 'update', data: 'first\nsecond' }]);
  });

  it('flushes a final unterminated event', () => {
    const decoder = new SseDecoder();
    decoder.push('event: run_completed\ndata: {}');
    expect(decoder.finish()).toEqual([{ event: 'run_completed', data: '{}' }]);
  });
});
