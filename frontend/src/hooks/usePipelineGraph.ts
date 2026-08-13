import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  addEdge,
  useEdgesState,
  useNodesState,
  useUpdateNodeInternals,
  type Connection,
  type Edge,
  type Node,
  type ReactFlowInstance,
  type Viewport,
} from '@xyflow/react';
import {
  createInitialEdges,
  createInitialNodes,
  MODULE_NODE_TYPES,
  NODE_COLORS,
  NODE_MODULE_TYPES,
} from '../config/pipeline';
import type {
  ModuleDefinition,
  ModuleType,
  WorkflowGraph,
  WorkflowRun,
  WorkflowViewport,
} from '../types';

interface PipelineGraphOptions {
  queryText: string;
  setQueryText: (text: string) => void;
  activeStep: number;
  modules: ModuleDefinition[];
}

const DEFAULT_VIEWPORT: WorkflowViewport = { x: 0, y: 0, zoom: 1 };
const EXECUTION_BRANCHES = new Set(['generated', 'cached']);
const BRANCH_COLORS: Record<string, string> = {
  generated: '#16a34a',
  cached: '#2563eb',
};
const FALLBACK_BRANCH_OUTPUTS: Partial<Record<ModuleType, Record<string, string>>> = {
  query_input: {
    generated: 'question_text',
    cached: 'cached_answer',
  },
};

function migrateLegacyConnections(graph: WorkflowGraph): WorkflowGraph {
  const moduleTypeByNodeId = new Map(
    graph.nodes.map((node) => [node.id, node.module_type])
  );
  const seenConnections = new Set<string>();
  const edges: WorkflowGraph['edges'] = [];

  for (const edge of graph.edges) {
    const sourceType = moduleTypeByNodeId.get(edge.source);
    const targetType = moduleTypeByNodeId.get(edge.target);
    // A node can be deleted before ReactFlow emits its connected-edge removal.
    // Never keep that stale edge in a saved graph or send it to DAG validation.
    if (!sourceType || !targetType) continue;
    let targetInput = edge.target_input;

    if (targetInput === 'input' && targetType === 'bm25_retriever') {
      if (sourceType === 'decomposer') targetInput = 'query_input';
      if (sourceType === 'cell_text_serializer') targetInput = 'document_input';
    }
    if (targetInput === 'input' && targetType === 'dense_retriever') {
      if (sourceType === 'embedder') targetInput = 'query_input';
      if (sourceType === 'vector_index_writer') targetInput = 'index_input';
    }

    const migratedEdge = { ...edge, target_input: targetInput };
    const connectionKey = JSON.stringify([
      migratedEdge.source,
      migratedEdge.target,
      migratedEdge.source_output ?? null,
      migratedEdge.target_input ?? null,
      migratedEdge.source_branch ?? null,
    ]);
    if (seenConnections.has(connectionKey)) continue;
    seenConnections.add(connectionKey);
    edges.push(migratedEdge);
  }

  return { ...graph, edges };
}

function objectConfig(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function numericRecord(value: unknown): Record<string, number> {
  return Object.fromEntries(
    Object.entries(objectConfig(value)).filter(
      (entry): entry is [string, number] => typeof entry[1] === 'number'
    )
  );
}

function moduleConfigDefaults(definition: ModuleDefinition | undefined): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(definition?.config_schema.properties ?? {}).flatMap(([field, schema]) =>
      schema.default === undefined ? [] : [[field, schema.default]]
    )
  );
}

const LEGACY_DECOMPOSER_SYSTEM_PROMPT_PREFIX = 'You are an expert financial DB query planner.';
const LEGACY_DECOMPOSER_USER_PROMPT = 'Decompose the following financial question into atomic subqueries:\nQuestion: {question}';

function moduleConfig(nodeType: string | undefined, value: unknown): Record<string, unknown> {
  const config = objectConfig(value);
  if (
    NODE_MODULE_TYPES[nodeType ?? ''] === 'decomposer'
    && typeof config.system_prompt === 'string'
    && config.system_prompt.startsWith(LEGACY_DECOMPOSER_SYSTEM_PROMPT_PREFIX)
    && config.user_prompt_template === LEGACY_DECOMPOSER_USER_PROMPT
  ) {
    const current = { ...config };
    delete current.system_prompt;
    delete current.user_prompt_template;
    return current;
  }
  return config;
}

function collectDescendantNodeIds(rootNodeId: string, graphEdges: Edge[]): Set<string> {
  const collected = new Set([rootNodeId]);
  const queue = [rootNodeId];

  while (queue.length > 0) {
    const sourceNodeId = queue.shift();
    graphEdges.forEach((edge) => {
      if (edge.source !== sourceNodeId || collected.has(edge.target)) return;
      collected.add(edge.target);
      queue.push(edge.target);
    });
  }
  return collected;
}

function summarizeDag(nodes: Node[], edges: Edge[]) {
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

export function usePipelineGraph(options: PipelineGraphOptions) {
  const {
    queryText,
    setQueryText,
    activeStep,
    modules,
  } = options;
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [viewport, setViewport] = useState<WorkflowViewport>(DEFAULT_VIEWPORT);
  const instanceRef = useRef<ReactFlowInstance | null>(null);
  const updateNodeInternals = useUpdateNodeInternals();
  const stoppedNodeIdsRef = useRef<Set<string>>(new Set());
  const viewportRef = useRef<WorkflowViewport>(DEFAULT_VIEWPORT);
  const nodeSequence = useRef(0);
  const edgeSequence = useRef(0);

  const sharedNodeData = useCallback(
    (nodeType?: string) => {
      const moduleType = NODE_MODULE_TYPES[nodeType ?? ''];
      const definition = modules.find((module) => module.type === moduleType);
      const branchOutputs = definition?.branch_outputs
        ?? FALLBACK_BRANCH_OUTPUTS[moduleType]
        ?? {};
      const shared = {
        queryText,
        setQueryText,
        activeStep,
        branchOutputs,
        outputBranches: Object.keys(branchOutputs),
        moduleDefinition: definition,
      };
      return shared;
    },
    [activeStep, modules, queryText, setQueryText]
  );

  const [nodes, setNodes, _onNodesChange] = useNodesState<Node>(
    createInitialNodes().map((node) => ({
      ...node,
      data: { ...node.data, ...sharedNodeData(node.type) },
    }))
  );
  const [edges, setEdges, _onEdgesChange] = useEdgesState(createInitialEdges());

  // When nodes are removed, also remove all edges connected to those nodes.
  // This prevents orphan/dangling edges that would fail backend validation.
  const onNodesChange = useCallback<typeof _onNodesChange>(
    (changes) => {
      const removedNodeIds = new Set(
        changes.filter((c) => c.type === 'remove').map((c) => c.id)
      );
      if (removedNodeIds.size > 0) {
        setEdges((currentEdges) =>
          currentEdges.filter(
            (e) => !removedNodeIds.has(e.source) && !removedNodeIds.has(e.target)
          )
        );
      }
      _onNodesChange(changes);
    },
    [_onNodesChange, setEdges]
  );

  const onNodesChange = useCallback<typeof _onNodesChange>(
    (changes) => {
      const removedNodeIds = new Set(
        changes.filter((change) => change.type === 'remove').map((change) => change.id)
      );
      if (removedNodeIds.size > 0) {
        setEdges((currentEdges) => currentEdges.filter(
          (edge) => !removedNodeIds.has(edge.source) && !removedNodeIds.has(edge.target)
        ));
      }
      _onNodesChange(changes);
    },
    [_onNodesChange, setEdges]
  );

  // Block automatic ReactFlow 'remove' events for edges only.
  // Edge removal is handled exclusively by the × button in CustomEdge (via deleteElements).
  // The keyboard shortcut (Backspace / Delete) is disabled via deleteKeyCode={null}
  // in PipelineCanvas, so only explicit UI interactions can delete anything.
  const onEdgesChange = useCallback<typeof _onEdgesChange>(
    (changes) => _onEdgesChange(changes),
    [_onEdgesChange]
  );

  const dagSummary = useMemo(() => summarizeDag(nodes, edges), [edges, nodes]);

  useEffect(() => {
    setNodes((currentNodes) => {
      const nodeById = new Map(currentNodes.map((node) => [node.id, node]));
      const incomingEdgeByTarget = new Map(
        edges.map((edge) => [edge.target, edge])
      );
      const inspectedModuleType = (
        nodeId: string,
        visited = new Set<string>(),
      ): ModuleType | undefined => {
        if (visited.has(nodeId)) return undefined;
        visited.add(nodeId);
        const incomingEdge = incomingEdgeByTarget.get(nodeId);
        const sourceNode = incomingEdge ? nodeById.get(incomingEdge.source) : undefined;
        const sourceModuleType = NODE_MODULE_TYPES[sourceNode?.type ?? ''];
        if (sourceModuleType === 'json_inspector' && sourceNode) {
          return inspectedModuleType(sourceNode.id, visited);
        }
        return sourceModuleType;
      };
      let changed = false;
      const nextNodes = currentNodes.map((node) => {
        if (NODE_MODULE_TYPES[node.type ?? ''] !== 'json_inspector') return node;
        const nextModuleType = inspectedModuleType(node.id);
        if (node.data.upstreamModuleType === nextModuleType) return node;
        changed = true;
        return {
          ...node,
          data: { ...node.data, upstreamModuleType: nextModuleType },
        };
      });
      return changed ? nextNodes : currentNodes;
    });
  }, [edges, setNodes]);

  const updateNodeConfig = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      setNodes((currentNodes) =>
        currentNodes.map((node) =>
          node.id === nodeId
            ? {
                ...node,
                data: {
                  ...node.data,
                  config: { ...objectConfig(node.data.config), ...patch },
                },
              }
            : node
        )
      );
    },
    [setNodes]
  );

  const updateNodeWidth = useCallback(
    (nodeId: string, width: number) => {
      setNodes((currentNodes) =>
        currentNodes.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, nodeWidth: width } }
            : node
        )
      );
      window.requestAnimationFrame(() => updateNodeInternals(nodeId));
    },
    [setNodes, updateNodeInternals]
  );

  const updateNodeColumnWidth = useCallback(
    (nodeId: string, column: string, width: number) => {
      setNodes((currentNodes) =>
        currentNodes.map((node) =>
          node.id === nodeId
            ? {
                ...node,
                data: {
                  ...node.data,
                  columnWidths: {
                    ...numericRecord(node.data.columnWidths),
                    [column]: width,
                  },
                },
              }
            : node
        )
      );
    },
    [setNodes]
  );

  const decorateNodeData = useCallback(
    (nodeId: string, nodeType: string | undefined, existing: Record<string, unknown>) => ({
      ...existing,
      ...sharedNodeData(nodeType),
      config: moduleConfig(nodeType, existing.config),
      onConfigChange: (patch: Record<string, unknown>) => updateNodeConfig(nodeId, patch),
      onNodeWidthChange: (width: number) => updateNodeWidth(nodeId, width),
      onColumnWidthChange: (column: string, width: number) =>
        updateNodeColumnWidth(nodeId, column, width),
    }),
    [sharedNodeData, updateNodeColumnWidth, updateNodeConfig, updateNodeWidth]
  );

  useEffect(() => {
    setNodes((currentNodes) =>
      currentNodes.map((node) => ({
        ...node,
        data: decorateNodeData(node.id, node.type, node.data),
      }))
    );

    setEdges((currentEdges) =>
      currentEdges.map((edge) => {
        const stageIndex = edge.data?.stageIndex;
        if (typeof stageIndex !== 'number') return edge;
        return {
          ...edge,
          data: {
            ...edge.data,
            active: activeStep === stageIndex,
            done: activeStep > stageIndex,
          },
        };
      })
    );
  }, [activeStep, decorateNodeData, setEdges, setNodes]);

  useEffect(() => {
    if (modules.length === 0) return;
    const frame = window.requestAnimationFrame(() => {
      nodes.forEach((node) => updateNodeInternals(node.id));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [modules, nodes.length, updateNodeInternals]);

  useEffect(() => {
    viewportRef.current = viewport;
  }, [viewport]);

  const createCustomNode = useCallback(
    (moduleType: ModuleType, position: { x: number; y: number }): Node => {
      const nodeId = `custom-node-${Date.now()}-${++nodeSequence.current}`;
      const nodeType = MODULE_NODE_TYPES[moduleType];
      const definition = modules.find((module) => module.type === moduleType);
      return {
        id: nodeId,
        type: nodeType,
        position,
        data: decorateNodeData(nodeId, nodeType, {
          config: moduleConfigDefaults(definition),
        }),
      };
    },
    [decorateNodeData, modules]
  );

  const addNode = useCallback(
    (moduleType: ModuleType) => {
      const offset = nodes.length * 16;
      const fallback = { x: 360 + offset, y: 260 + offset };
      const position = reactFlowInstance
        ? reactFlowInstance.screenToFlowPosition({
            x: window.innerWidth / 2,
            y: window.innerHeight / 2,
          })
        : fallback;
      setNodes((currentNodes) => currentNodes.concat(createCustomNode(moduleType, position)));
    },
    [createCustomNode, nodes.length, reactFlowInstance, setNodes]
  );

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const moduleType = event.dataTransfer.getData('application/reactflow') as ModuleType;
      if (!moduleType || !reactFlowInstance) return;
      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      setNodes((currentNodes) => currentNodes.concat(createCustomNode(moduleType, position)));
    },
    [createCustomNode, reactFlowInstance, setNodes]
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      const sourceBranch = connection.sourceHandle && EXECUTION_BRANCHES.has(connection.sourceHandle)
        ? connection.sourceHandle
        : undefined;
      const sourceNode = nodes.find((node) => node.id === connection.source);
      const targetNode = nodes.find((node) => node.id === connection.target);
      const branchOutputs = objectConfig(sourceNode?.data.branchOutputs);
      const sourceDefinition = sourceNode?.data.moduleDefinition as ModuleDefinition | undefined;
      const targetDefinition = targetNode?.data.moduleDefinition as ModuleDefinition | undefined;
      const sourceOutput = connection.sourceHandle && sourceDefinition?.outputs.includes(connection.sourceHandle)
        ? connection.sourceHandle
        : sourceBranch && typeof branchOutputs[sourceBranch] === 'string'
          ? branchOutputs[sourceBranch]
          : sourceDefinition?.outputs.length === 1
            ? sourceDefinition.outputs[0]
            : connection.sourceHandle && connection.sourceHandle !== 'out'
              ? connection.sourceHandle
              : undefined;
      const targetInput = connection.targetHandle && targetDefinition?.inputs.includes(connection.targetHandle)
        ? connection.targetHandle
        : connection.targetHandle && connection.targetHandle !== 'in'
          ? connection.targetHandle
          : targetDefinition?.inputs.length === 1
            ? targetDefinition.inputs[0]
            : undefined;
      const sourceColor = NODE_COLORS[sourceNode?.type ?? ''] ?? NODE_COLORS.queryNode;
      setEdges((currentEdges) =>
        addEdge(
          {
            ...connection,
            id: `edge-${Date.now()}-${++edgeSequence.current}`,
            type: 'customEdge',
            data: {
              active: false,
              done: false,
              color: sourceBranch ? BRANCH_COLORS[sourceBranch] : sourceColor,
              source_branch: sourceBranch,
              source_output: sourceOutput,
              target_input: targetInput,
            },
          },
          currentEdges
        )
      );
    },
    [nodes, setEdges]
  );

  const onInit = useCallback((instance: ReactFlowInstance) => {
    instanceRef.current = instance;
    setReactFlowInstance(instance);
  }, []);

  const onMoveEnd = useCallback((_event: MouseEvent | TouchEvent | null, next: Viewport) => {
    const nextViewport = { x: next.x, y: next.y, zoom: next.zoom };
    viewportRef.current = nextViewport;
    setViewport(nextViewport);
  }, []);

  const exportGraph = useCallback((): WorkflowGraph => migrateLegacyConnections({
    nodes: nodes.flatMap((node) => {
      const moduleType = NODE_MODULE_TYPES[node.type ?? ''];
      if (!moduleType) return [];
      return [{
        id: node.id,
        module_type: moduleType,
        position: { x: node.position.x, y: node.position.y },
        config: objectConfig(node.data.config),
        values: moduleType === 'query_input' && typeof node.data.queryText === 'string'
          ? { query: node.data.queryText }
          : {},
        ui: {
          ...(typeof node.data.nodeWidth === 'number'
            ? { width: node.data.nodeWidth }
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
        ...(typeof edge.data?.source_branch === 'string' &&
        EXECUTION_BRANCHES.has(edge.data.source_branch)
          ? { source_branch: edge.data.source_branch as WorkflowGraph['edges'][number]['source_branch'] }
          : {}),
      };
    }),
    viewport: viewportRef.current,
  }), [edges, nodes]);

  const replaceGraph = useCallback(
    (graph: WorkflowGraph) => {
      const migratedGraph = migrateLegacyConnections(graph);
      const savedQuery = migratedGraph.nodes.find(
        (workflowNode) => workflowNode.module_type === 'query_input'
      )?.values?.query;
      setQueryText(typeof savedQuery === 'string' ? savedQuery : '');

      stoppedNodeIdsRef.current = new Set(
        migratedGraph.nodes
          .filter((workflowNode) => workflowNode.ui?.execution_stopped === true)
          .map((workflowNode) => workflowNode.id)
      );

      setNodes(
        migratedGraph.nodes.map((workflowNode) => {
          const nodeType = MODULE_NODE_TYPES[workflowNode.module_type];
          return {
            id: workflowNode.id,
            type: nodeType,
            position: workflowNode.position,
            data: decorateNodeData(workflowNode.id, nodeType, {
              config: workflowNode.config,
              nodeWidth: workflowNode.ui?.width ?? undefined,
              columnWidths: workflowNode.ui?.column_widths ?? {},
              executionStopped: workflowNode.ui?.execution_stopped === true,
            }),
          };
        })
      );
      setEdges(
        migratedGraph.edges.map((workflowEdge): Edge => {
          const targetNode = migratedGraph.nodes.find((node) => node.id === workflowEdge.target);
          const targetDefinition = modules.find(
            (module) => module.type === targetNode?.module_type
          );
          const sourceNode = migratedGraph.nodes.find((node) => node.id === workflowEdge.source);
          const sourceDefinition = modules.find(
            (module) => module.type === sourceNode?.module_type
          );
          const hasMultipleInputs = (targetDefinition?.inputs.length ?? 0) > 1;
          const targetHandle = hasMultipleInputs && workflowEdge.target_input
            ? workflowEdge.target_input
            : 'in';
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
        })
      );
      viewportRef.current = migratedGraph.viewport;
      setViewport(migratedGraph.viewport);
      window.requestAnimationFrame(() => {
        void instanceRef.current?.setViewport(migratedGraph.viewport);
        migratedGraph.nodes.forEach((workflowNode) => updateNodeInternals(workflowNode.id));
      });
    },
    [decorateNodeData, modules, setEdges, setNodes, setQueryText, updateNodeInternals]
  );

  const applyRun = useCallback(
    (run: WorkflowRun) => {
      const stoppedNodeIds = stoppedNodeIdsRef.current;
      setNodes((currentNodes) =>
        currentNodes.map((node) => {
          const state = run.nodes[node.id];
          if (!state) return node;
          if (stoppedNodeIds.has(node.id)) {
            return {
              ...node,
              data: {
                ...node.data,
                executionStopped: true,
                executionState: 'idle',
                executionOutput: null,
                executionInput: null,
                executionError: null,
                executionOutcome: null,
                cacheHit: false,
                batchIndex: undefined,
              },
            };
          }
          return {
            ...node,
            data: {
              ...node.data,
              executionStopped: false,
              executionState: state.status,
              executionOutput: state.output,
              executionInput: state.input_payload,
              executionError: state.error,
              executionOutcome: state.outcome,
              cacheHit: state.cache_hit,
              batchIndex: state.batch_index,
              elapsedMs: state.elapsed_ms,
              costUsd: state.cost_usd,
              usage: state.usage,
            },
          };
        })
      );
      setEdges((currentEdges) =>
        currentEdges.map((edge) => {
          if (stoppedNodeIds.has(edge.source) || stoppedNodeIds.has(edge.target)) {
            return {
              ...edge,
              data: { ...edge.data, active: false, done: false },
            };
          }
          const sourceState = run.nodes[edge.source]?.status;
          const sourceOutcome = run.nodes[edge.source]?.outcome;
          const targetState = run.nodes[edge.target]?.status;
          const sourceBranch = edge.data?.source_branch;
          const branchMatches = typeof sourceBranch === 'string'
            ? sourceOutcome === sourceBranch
            : sourceState === 'succeeded';
          return {
            ...edge,
            data: {
              ...edge.data,
              done: branchMatches && targetState === 'succeeded',
              active: branchMatches && targetState === 'running',
            },
          };
        })
      );
    },
    [setEdges, setNodes]
  );

  const clearExecutionState = useCallback(() => {
    stoppedNodeIdsRef.current = new Set();
    setNodes((currentNodes) =>
      currentNodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          executionStopped: false,
          executionState: undefined,
          executionOutput: null,
          executionInput: null,
          executionError: null,
          executionOutcome: null,
          cacheHit: false,
          batchIndex: undefined,
        },
      }))
    );
    setEdges((currentEdges) =>
      currentEdges.map((edge) => ({
        ...edge,
        data: { ...edge.data, active: false, done: false },
      }))
    );
  }, [setEdges, setNodes]);

  const clearNodeExecutionState = useCallback((nodeId: string) => {
    const resetNodeIds = collectDescendantNodeIds(nodeId, edges);
    stoppedNodeIdsRef.current = new Set([
      ...stoppedNodeIdsRef.current,
      ...resetNodeIds,
    ]);
    setNodes((currentNodes) =>
      currentNodes.map((node) =>
        resetNodeIds.has(node.id)
          ? {
              ...node,
              data: {
                ...node.data,
                executionStopped: true,
                executionState: 'idle',
                executionOutput: null,
                executionInput: null,
                executionError: null,
                executionOutcome: null,
                cacheHit: false,
                batchIndex: undefined,
              },
            }
          : node
      )
    );
    setEdges((currentEdges) =>
      currentEdges.map((edge) =>
        resetNodeIds.has(edge.source) || resetNodeIds.has(edge.target)
          ? { ...edge, data: { ...edge.data, active: false, done: false } }
          : edge
      )
    );
  }, [edges, setEdges, setNodes]);

  const resumeNodeExecution = useCallback((nodeId: string) => {
    const resumedNodeIds = collectDescendantNodeIds(nodeId, edges);
    stoppedNodeIdsRef.current = new Set(
      [...stoppedNodeIdsRef.current].filter((stoppedId) => !resumedNodeIds.has(stoppedId))
    );
    setNodes((currentNodes) =>
      currentNodes.map((node) =>
        resumedNodeIds.has(node.id)
          ? {
              ...node,
              data: { ...node.data, executionStopped: false },
            }
          : node
      )
    );
  }, [edges, setNodes]);

  const clearGraph = useCallback(() => {
    setNodes([]);
    setEdges([]);
  }, [setEdges, setNodes]);

  const selectNode = useCallback((nodeId: string) => {
    setNodes((currentNodes) => currentNodes.map((node) => ({
      ...node,
      selected: node.id === nodeId,
    })));
  }, [setNodes]);

  const duplicateNode = useCallback((nodeId: string) => {
    setNodes((currentNodes) => {
      const original = currentNodes.find((node) => node.id === nodeId);
      if (!original) return currentNodes;
      const clone: Node = {
        ...original,
        id: `node-${Date.now()}`,
        position: { x: original.position.x + 36, y: original.position.y + 36 },
        data: { ...original.data, executionState: undefined, executionOutput: null, executionError: null },
        selected: true,
      };
      return currentNodes.map((node): Node => ({ ...node, selected: false })).concat(clone);
    });
  }, [setNodes]);

  /** Explicitly remove a node and all edges connected to it. */
  const deleteNode = useCallback(
    (nodeId: string) => {
      setEdges((currentEdges) =>
        currentEdges.filter(
          (edge) => edge.source !== nodeId && edge.target !== nodeId
        )
      );
      setNodes((currentNodes) =>
        currentNodes.filter((node) => node.id !== nodeId)
      );
    },
    [setEdges, setNodes]
  );

  return {
    nodes,
    edges,
    viewport,
    onNodesChange,
    onEdgesChange,
    onConnect,
    onDrop,
    onDragOver,
    onInit,
    onMoveEnd,
    addNode,
    deleteNode,
    updateNodeConfig,
    exportGraph,
    replaceGraph,
    applyRun,
    clearExecutionState,
    clearNodeExecutionState,
    resumeNodeExecution,
    clearGraph,
    selectNode,
    duplicateNode,
    batchCount: dagSummary.batchCount,
    hasCycle: dagSummary.hasCycle,
  };
}
