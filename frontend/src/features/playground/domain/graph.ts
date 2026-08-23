export interface GraphNodeRef {
  readonly id: string;
}

export interface GraphEdgeRef {
  readonly source: string;
  readonly target: string;
}

export interface DagSummary {
  readonly batchCount: number;
  readonly hasCycle: boolean;
}

export function collectDescendantNodeIds(
  rootNodeId: string,
  edges: GraphEdgeRef[],
): Set<string> {
  const collected = new Set([rootNodeId]);
  const queue = [rootNodeId];
  while (queue.length > 0) {
    const sourceNodeId = queue.shift();
    edges.forEach((edge) => {
      if (edge.source !== sourceNodeId || collected.has(edge.target)) return;
      collected.add(edge.target);
      queue.push(edge.target);
    });
  }
  return collected;
}

export function summarizeDag(
  nodes: GraphNodeRef[],
  edges: GraphEdgeRef[],
): DagSummary {
  if (nodes.length === 0) return { batchCount: 0, hasCycle: false };

  const nodeIds = new Set(nodes.map((node) => node.id));
  const indegree = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(nodes.map((node) => [node.id, [] as string[]]));
  const dependencies = new Set<string>();

  edges.forEach((edge) => {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) return;
    const dependency = `${edge.source}\u0000${edge.target}`;
    if (dependencies.has(dependency)) return;
    dependencies.add(dependency);
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
    outgoing.get(edge.source)?.push(edge.target);
  });

  let currentBatch = nodes
    .map((node) => node.id)
    .filter((nodeId) => indegree.get(nodeId) === 0);
  let processedCount = 0;
  let batchCount = 0;

  while (currentBatch.length > 0) {
    batchCount += 1;
    processedCount += currentBatch.length;
    const nextBatch: string[] = [];
    currentBatch.forEach((nodeId) => {
      outgoing.get(nodeId)?.forEach((targetId) => {
        const nextIndegree = (indegree.get(targetId) ?? 0) - 1;
        indegree.set(targetId, nextIndegree);
        if (nextIndegree === 0) nextBatch.push(targetId);
      });
    });
    currentBatch = nextBatch;
  }

  const hasCycle = processedCount !== nodes.length;
  return { batchCount: hasCycle ? 0 : batchCount, hasCycle };
}
