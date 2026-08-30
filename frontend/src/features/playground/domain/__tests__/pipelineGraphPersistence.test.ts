import type { Edge, Node } from '@xyflow/react';
import { describe, expect, it, vi } from 'vitest';
import {
  restorePipelineEdges,
  restorePipelineNodes,
  serializePipelineGraph,
} from '../pipelineGraphPersistence';
import type { ModuleDefinition, WorkflowGraph } from '../../types';

function moduleDefinition(
  type: string,
  inputs: string[],
  outputs: string[],
): ModuleDefinition {
  return {
    type,
    label: type,
    category: 'logic',
    description: '',
    inputs,
    outputs,
    branch_outputs: {},
    config_fields: [],
    config_presets: [],
    raw_input: false,
    raw_output: false,
    version: '1',
    cacheable: false,
    task: {
      engine: 'kubernetes',
      enabled: true,
      retries: 0,
      retry_delay_seconds: 0,
      timeout_seconds: null,
      tags: [],
      resource_profile: 'interactive',
    },
    input_schema: {},
    config_schema: {},
    output_schema: {},
    execution_schema: {},
    documentation_url: '',
    branch_schemas: {},
  };
}

const workflowGraph: WorkflowGraph = {
  nodes: [
    {
      id: 'query',
      module_type: 'query_input',
      position: { x: 10, y: 20 },
      config: { locale: 'ko' },
      values: { query: 'runtime only', audience: 'finance' },
      ui: { width: 320, execution_stopped: true, column_widths: { input: 140 } },
    },
    {
      id: 'reader',
      module_type: 'reader',
      position: { x: 200, y: 20 },
      config: {},
      values: {},
    },
  ],
  edges: [{
    id: 'edge-1',
    source: 'query',
    target: 'reader',
    source_output: 'generated_answer',
    target_input: 'context',
    source_branch: 'generated',
  }],
  viewport: { x: 4, y: 8, zoom: 0.9 },
};

describe('pipeline graph persistence', () => {
  it('serializes persistent node values and explicit edge contracts', () => {
    const nodes: Node[] = workflowGraph.nodes.map((node) => ({
      id: node.id,
      type: node.module_type === 'query_input' ? 'queryNode' : 'readerNode',
      position: node.position,
      data: {
        moduleType: node.module_type,
        config: node.config,
        values: node.values,
        nodeWidth: node.ui?.width,
        executionStopped: node.ui?.execution_stopped,
        columnWidths: node.ui?.column_widths,
      },
    }));
    const edges: Edge[] = [{
      id: 'edge-1',
      source: 'query',
      target: 'reader',
      sourceHandle: 'generated',
      targetHandle: 'context',
      data: {
        source_branch: 'generated',
        source_output: 'generated_answer',
        target_input: 'context',
      },
    }];

    const serialized = serializePipelineGraph(nodes, edges, workflowGraph.viewport);

    expect(serialized.nodes[0].values).toEqual({ audience: 'finance' });
    expect(serialized.nodes[0].ui).toMatchObject({
      width: 320,
      execution_stopped: true,
      column_widths: { input: 140 },
    });
    expect(serialized.edges[0]).toEqual(workflowGraph.edges[0]);
  });

  it('restores node UI data and validated connection handles', () => {
    const decorate = vi.fn((_id, _type, data: Record<string, unknown>) => ({
      ...data,
      decorated: true,
    }));
    const modules = [
      moduleDefinition('query_input', [], ['generated_answer', 'fallback']),
      moduleDefinition('reader', ['context'], ['answer']),
    ];

    const nodes = restorePipelineNodes(workflowGraph, decorate);
    const edges = restorePipelineEdges(workflowGraph, modules);

    expect(nodes[0].data).toMatchObject({
      moduleType: 'query_input',
      nodeWidth: 320,
      executionStopped: true,
      decorated: true,
    });
    expect(edges[0]).toMatchObject({
      sourceHandle: 'generated',
      targetHandle: 'context',
      data: { color: '#16a34a', active: false, done: false },
    });
  });
});
