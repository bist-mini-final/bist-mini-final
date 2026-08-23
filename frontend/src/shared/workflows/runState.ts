import type { WorkflowRun } from './types';

type RunNodeState = WorkflowRun['nodes'][string];

function batchStatus(
  nodeIds: string[],
  nodes: WorkflowRun['nodes'],
): WorkflowRun['batches'][number]['status'] {
  const statuses = nodeIds.map((nodeId) => nodes[nodeId]?.status);
  if (statuses.some((status) => status === 'failed')) return 'failed';
  if (statuses.some((status) => status === 'running')) return 'running';
  if (statuses.every((status) => status === 'succeeded' || status === 'skipped')) {
    return 'completed';
  }
  return 'pending';
}

/** Merges one persisted node event and derives batch/run progress without another API read. */
export function mergeRunNodeUpdate(
  run: WorkflowRun,
  update: Partial<RunNodeState> & Pick<RunNodeState, 'node_id'>,
): WorkflowRun {
  const current = run.nodes[update.node_id];
  if (!current) return run;
  const nodes = {
    ...run.nodes,
    [update.node_id]: { ...current, ...update },
  };
  const batches = run.batches.map((batch) => ({
    ...batch,
    status: batchStatus(batch.node_ids, nodes),
  }));
  const statuses = batches.map((batch) => batch.status);
  const status = statuses.some((batch) => batch === 'failed')
    ? 'failed'
    : statuses.every((batch) => batch === 'completed')
      ? 'completed'
      : statuses.some((batch) => batch === 'running' || batch === 'completed')
        ? 'running'
        : run.status;
  return { ...run, nodes, batches, status };
}
