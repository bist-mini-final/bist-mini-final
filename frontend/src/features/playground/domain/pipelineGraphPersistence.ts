import type { Edge, Node } from '@xyflow/react';
import { MODULE_NODE_TYPES, NODE_COLORS } from '../config/pipeline';
import { nodeModuleType } from '../adapters/reactFlowGraph';
import { persistentNodeValues } from './execution';
import { numericRecord, objectConfig, resolveTargetInput } from './moduleDefaults';
import type {
  ModuleDefinition,
  ModuleType,
  WorkflowGraph,
  WorkflowViewport,
} from '../types';

export const EXECUTION_BRANCHES = new Set(['generated', 'cached']);
export const BRANCH_COLORS: Readonly<Record<string, string>> = {
  generated: '#16a34a',
  cached: '#2563eb',
};

type DecorateNodeData = (
  nodeId: string,
  nodeType: string | undefined,
  data: Record<string, unknown>,
) => Record<string, unknown>;

export function serializePipelineGraph(
  nodes: readonly Node[],
  edges: readonly Edge[],
  viewport: WorkflowViewport,
): WorkflowGraph {
  return {
    nodes: nodes.flatMap((node) => {
      const moduleType = nodeModuleType(node);
      if (!moduleType) return [];
      return [{
        id: node.id,
        module_type: moduleType,
        position: { x: node.position.x, y: node.position.y },
        config: objectConfig(node.data.config),
        values: persistentNodeValues(moduleType, objectConfig(node.data.values)),
        ui: {
          ...(typeof node.data.nodeWidth === 'number'
            ? { width: node.data.nodeWidth }
            : {}),
          ...(typeof node.data.nodeHeight === 'number'
            ? { height: node.data.nodeHeight }
            : {}),
          execution_stopped: node.data.executionStopped === true,
          column_widths: numericRecord(node.data.columnWidths),
        },
      }];
    }),
    edges: edges.map((edge) => {
      const sourceOutput = typeof edge.data?.source_output === 'string' && edge.data.source_output
        ? edge.data.source_output
        : typeof edge.sourceHandle === 'string' && edge.sourceHandle !== 'out'
          ? edge.sourceHandle
          : undefined;
      const targetInput = typeof edge.data?.target_input === 'string' && edge.data.target_input
        ? edge.data.target_input
        : typeof edge.targetHandle === 'string' && edge.targetHandle !== 'in'
          ? edge.targetHandle
          : undefined;
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        ...(sourceOutput ? { source_output: sourceOutput } : {}),
        ...(targetInput ? { target_input: targetInput } : {}),
        ...(typeof edge.data?.source_branch === 'string'
        && EXECUTION_BRANCHES.has(edge.data.source_branch)
          ? {
              source_branch: edge.data
                .source_branch as WorkflowGraph['edges'][number]['source_branch'],
            }
          : {}),
      };
    }),
    viewport,
  };
}

export function restorePipelineNodes(
  graph: WorkflowGraph,
  decorateNodeData: DecorateNodeData,
): Node[] {
  return graph.nodes.map((workflowNode) => {
    const nodeType = MODULE_NODE_TYPES[workflowNode.module_type] ?? 'generic_module';
    return {
      id: workflowNode.id,
      type: nodeType,
      position: workflowNode.position,
      data: decorateNodeData(workflowNode.id, nodeType, {
        moduleType: workflowNode.module_type,
        config: workflowNode.config,
        values: workflowNode.values,
        nodeWidth: workflowNode.ui?.width ?? undefined,
        nodeHeight: workflowNode.ui?.height ?? undefined,
        columnWidths: workflowNode.ui?.column_widths ?? {},
        executionStopped: workflowNode.ui?.execution_stopped === true,
      }),
    };
  });
}

export function restorePipelineEdges(
  graph: WorkflowGraph,
  modules: readonly ModuleDefinition[],
): Edge[] {
  const workflowNodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const moduleByType = new Map<ModuleType, ModuleDefinition>(
    modules.map((module) => [module.type, module]),
  );

  return graph.edges.map((workflowEdge): Edge => {
    const targetNode = workflowNodeById.get(workflowEdge.target);
    const targetDefinition = targetNode
      ? moduleByType.get(targetNode.module_type)
      : undefined;
    const sourceNode = workflowNodeById.get(workflowEdge.source);
    const sourceDefinition = sourceNode
      ? moduleByType.get(sourceNode.module_type)
      : undefined;
    const targetHandle = resolveTargetInput(targetDefinition, workflowEdge.target_input) ?? 'in';
    const hasMultipleOutputs = (sourceDefinition?.outputs.length ?? 0) > 1
      || Object.keys(sourceDefinition?.branch_outputs ?? {}).length > 0;
    const sourceHandle = workflowEdge.source_branch
      ?? (hasMultipleOutputs && workflowEdge.source_output ? workflowEdge.source_output : 'out');

    return {
      id: workflowEdge.id,
      source: workflowEdge.source,
      target: workflowEdge.target,
      sourceHandle,
      targetHandle,
      type: 'customEdge',
      data: {
        active: false,
        done: false,
        source_output: workflowEdge.source_output,
        target_input: workflowEdge.target_input,
        source_branch: workflowEdge.source_branch,
        color: workflowEdge.source_branch
          ? BRANCH_COLORS[workflowEdge.source_branch]
          : NODE_COLORS.queryNode,
      },
    };
  });
}
