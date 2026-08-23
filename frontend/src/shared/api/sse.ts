import { ApiError, requestResponse } from './httpClient';

export interface SseMessage {
  event: string;
  data: string;
}

function parseEventBlock(block: string): SseMessage | null {
  let event = 'message';
  const data: string[] = [];

  for (const line of block.split(/\r\n|\n|\r/)) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    const rawValue = separator === -1 ? '' : line.slice(separator + 1);
    const value = rawValue.startsWith(' ') ? rawValue.slice(1) : rawValue;
    if (field === 'event') event = value;
    if (field === 'data') data.push(value);
  }

  return data.length > 0 ? { event, data: data.join('\n') } : null;
}

/** Incrementally decodes EventSource frames across arbitrary network chunks. */
export class SseDecoder {
  private buffer = '';

  push(chunk: string): SseMessage[] {
    this.buffer += chunk;
    const blocks = this.buffer.split(/\r\n\r\n|\n\n|\r\r/);
    this.buffer = blocks.pop() ?? '';
    return blocks.flatMap((block) => {
      const event = parseEventBlock(block);
      return event ? [event] : [];
    });
  }

  finish(chunk = ''): SseMessage[] {
    this.buffer += chunk;
    const trailing = this.buffer;
    this.buffer = '';
    const event = parseEventBlock(trailing);
    return event ? [event] : [];
  }
}

export interface JsonSseMessage {
  readonly event: string;
  readonly data: unknown;
}

/** Opens and incrementally consumes a JSON SSE response through the shared API client. */
export async function streamJsonEvents(
  endpoint: string,
  onEvent: (message: JsonSseMessage) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await requestResponse(endpoint, {
    headers: { Accept: 'text/event-stream' },
    signal,
    timeout: false,
  });
  const reader = response.body?.getReader();
  if (!reader) throw new ApiError('스트림 응답 본문을 읽을 수 없습니다.', 500);

  const textDecoder = new TextDecoder();
  const sseDecoder = new SseDecoder();
  const emit = (message: SseMessage): void => {
    try {
      onEvent({ event: message.event, data: JSON.parse(message.data) as unknown });
    } catch {
      onEvent({ event: message.event, data: message.data });
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      sseDecoder.push(textDecoder.decode(value, { stream: true })).forEach(emit);
    }
    sseDecoder.finish(textDecoder.decode()).forEach(emit);
  } finally {
    reader.releaseLock();
  }
}
