import { requestJson } from '../api/httpClient';
import { streamJsonEvents, type JsonSseMessage } from '../api/sse';
import { mergeRunNodeUpdate } from './runState';
import type { WorkflowRun } from './types';

export interface WorkflowRunEvent extends JsonSseMessage {}

interface ObserveWorkflowRunOptions {
  readonly initialRun?: WorkflowRun;
  readonly signal?: AbortSignal;
  readonly onEvent?: (event: WorkflowRunEvent) => void;
  readonly onRun?: (run: WorkflowRun, event: WorkflowRunEvent) => void;
}

function isTerminal(run: WorkflowRun | undefined): run is WorkflowRun {
  return run !== undefined
    && (run.status === 'completed' || run.status === 'failed' || run.status === 'paused');
}

function nodeUpdate(data: unknown): { node_id: string } | null {
  if (!data || typeof data !== 'object' || !('node_id' in data)) return null;
  return typeof data.node_id === 'string' ? data as { node_id: string } : null;
}

function completedRun(data: unknown): WorkflowRun | null {
  if (!data || typeof data !== 'object' || !('run' in data)) return null;
  const run = data.run;
  return run && typeof run === 'object' ? run as WorkflowRun : null;
}

const NODE_EVENTS = new Set([
  'node_progress',
  'node_started',
  'node_completed',
  'node_failed',
]);
const TERMINAL_EVENTS = new Set(['run_completed', 'run_finished', 'run_failed']);

export function isWorkflowNodeEvent(event: string): boolean {
  return NODE_EVENTS.has(event);
}

export function isWorkflowTerminalEvent(event: string): boolean {
  return TERMINAL_EVENTS.has(event);
}

function reconnectDelay(signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(signal.reason);
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, 500);
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(signal.reason);
    }, { once: true });
  });
}

/** Observes any persisted workflow run through the shared backend SSE core. */
export async function observeWorkflowRun(
  runId: string,
  options: ObserveWorkflowRunOptions = {},
): Promise<WorkflowRun> {
  let current = options.initialRun;
  const endpoint = `/api/runs/${encodeURIComponent(runId)}/stream`;

  while (!options.signal?.aborted) {
    try {
      await streamJsonEvents(endpoint, (event) => {
        options.onEvent?.(event);
        if (
          current
          && isWorkflowNodeEvent(event.event)
        ) {
          const update = nodeUpdate(event.data);
          if (update) current = mergeRunNodeUpdate(current, update);
        } else if (isWorkflowTerminalEvent(event.event)) {
          current = completedRun(event.data) ?? current;
        }
        if (current) options.onRun?.(current, event);
      }, options.signal);
    } catch (error) {
      if (options.signal?.aborted) throw error;
    }

    if (isTerminal(current)) return current;
    current = await requestJson<WorkflowRun>(
      `/api/runs/${encodeURIComponent(runId)}`,
      { signal: options.signal },
    );
    options.onRun?.(current, { event: 'run_snapshot', data: current });
    if (isTerminal(current)) return current;
    await reconnectDelay(options.signal);
  }

  throw options.signal?.reason ?? new DOMException('Aborted', 'AbortError');
}
