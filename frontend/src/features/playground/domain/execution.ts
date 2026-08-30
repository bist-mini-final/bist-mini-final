import type { WorkflowGraph, WorkflowRun } from '../types';
export { mergeRunNodeUpdate } from '../../../shared/workflows/runState';

type JsonRecord = Record<string, unknown>;

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(
    Object.entries(value as JsonRecord)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, entry]) => [key, canonicalValue(entry)])
  );
}

function definitionValues(
  moduleType: string,
  values: JsonRecord | undefined,
): JsonRecord {
  if (moduleType !== 'query_input') return values ?? {};
  const definition = { ...values };
  delete definition.query;
  return definition;
}

export function persistentNodeValues(
  moduleType: string,
  values: JsonRecord | undefined,
): JsonRecord {
  return definitionValues(moduleType, values);
}

export function workflowRuntimeInputs(
  graph: WorkflowGraph,
  query: string,
): Record<string, JsonRecord> {
  return Object.fromEntries(
    graph.nodes
      .filter((node) => node.module_type === 'query_input')
      .map((node) => [node.id, { query }])
  );
}

export function executionDefinitionFingerprint(graph: WorkflowGraph): string {
  const definition = {
    nodes: (graph.nodes ?? [])
      .map(({ id, module_type, config, values }) => ({
        id,
        module_type,
        config: config ?? {},
        values: definitionValues(module_type, values),
      }))
      .sort((left, right) => left.id.localeCompare(right.id)),
    edges: (graph.edges ?? [])
      .map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        source_output: edge.source_output ?? null,
        target_input: edge.target_input ?? null,
        source_branch: edge.source_branch ?? null,
      }))
      .sort((left, right) => left.id.localeCompare(right.id)),
  };
  return JSON.stringify(canonicalValue(definition));
}

export function executionRunMatchesRequest(
  run: WorkflowRun,
  graph: WorkflowGraph,
  query: string,
): boolean {
  return executionDefinitionFingerprint(run.graph) === executionDefinitionFingerprint(graph)
    && JSON.stringify(canonicalValue(run.runtime_inputs))
      === JSON.stringify(canonicalValue(workflowRuntimeInputs(graph, query)));
}

export function runtimeQueryFromRun(run: WorkflowRun): string | undefined {
  const queryNode = run.graph.nodes.find(
    (node) => node.module_type === 'query_input'
  );
  const query = queryNode ? run.runtime_inputs[queryNode.id]?.query : undefined;
  return typeof query === 'string' ? query : undefined;
}
