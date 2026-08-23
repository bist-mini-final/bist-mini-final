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
  MODULE_NODE_TYPES,
  NODE_COLORS,
  NODE_MODULE_TYPES,
} from '../config/pipeline';
import { nodeModuleType } from '../adapters/reactFlowGraph';
import { collectDescendantNodeIds, summarizeDag } from '../domain/graph';
import { persistentNodeValues, runtimeQueryFromRun } from '../domain/execution';
import {
  moduleConfigDefaults,
  moduleInputDefaults,
  numericRecord,
  objectConfig,
  resolveTargetInput,
} from '../domain/moduleDefaults';
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
    (nodeType?: string, explicitModuleType?: ModuleType) => {
      const moduleType = explicitModuleType ?? NODE_MODULE_TYPES[nodeType ?? ''];
      const definition = modules.find((module) => module.type === moduleType);
      const branchOutputs = definition?.branch_outputs ?? {};
      const shared = {
        queryText,
        setQueryText,
        activeStep,
        branchOutputs,
        outputBranches: Object.keys(branchOutputs),
        moduleDefinition: definition,
        moduleType,
      };
      return shared;
    },
    [activeStep, modules, queryText, setQueryText]
  );

  const [nodes, setNodes, _onNodesChange] = useNodesState<Node>(
    []
  );
  const [edges, setEdges, _onEdgesChange] = useEdgesState<Edge>([]);

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

  const onReadOnlyNodesChange = useCallback<typeof _onNodesChange>(
    (changes) => {
      const dimensions = changes.filter((change) => change.type === 'dimensions');
      if (dimensions.length > 0) _onNodesChange(dimensions);
    },
    [_onNodesChange]
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

  const updateNodeValues = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      setNodes((currentNodes) =>
        currentNodes.map((node) =>
          node.id === nodeId
            ? {
                ...node,
                data: {
                  ...node.data,
                  values: { ...objectConfig(node.data.values), ...patch },
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

  const updateNodeHeight = useCallback(
    (nodeId: string, height: number) => {
      setNodes((currentNodes) =>
        currentNodes.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, nodeHeight: height } }
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
    (nodeId: string, nodeType: string | undefined, existing: Record<string, unknown>) => {
      const explicitModuleType = typeof existing.moduleType === 'string'
        ? existing.moduleType as ModuleType
        : undefined;
      return {
        ...existing,
        ...sharedNodeData(nodeType, explicitModuleType),
        config: objectConfig(existing.config),
        values: objectConfig(existing.values),
        onConfigChange: (patch: Record<string, unknown>) => updateNodeConfig(nodeId, patch),
        onValuesChange: (patch: Record<string, unknown>) => updateNodeValues(nodeId, patch),
        onNodeWidthChange: (width: number) => updateNodeWidth(nodeId, width),
        onNodeHeightChange: (height: number) => updateNodeHeight(nodeId, height),
        onColumnWidthChange: (column: string, width: number) =>
          updateNodeColumnWidth(nodeId, column, width),
      };
    },
    [sharedNodeData, updateNodeColumnWidth, updateNodeConfig, updateNodeHeight, updateNodeValues, updateNodeWidth]
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
    const moduleTypeByNodeId = new Map(
      nodes.flatMap((node) => {
        const moduleType = nodeModuleType(node);
        return moduleType ? [[node.id, moduleType] as const] : [];
      })
    );
    const definitionByType = new Map(modules.map((module) => [module.type, module]));

    setEdges((currentEdges) => {
      let changed = false;
      const nextEdges = currentEdges.map((edge) => {
        const targetDefinition = definitionByType.get(moduleTypeByNodeId.get(edge.target) ?? '');
        const targetInput = resolveTargetInput(
          targetDefinition,
          edge.data?.target_input ?? edge.targetHandle,
        );
        if (!targetInput || (
          edge.targetHandle === targetInput
          && edge.data?.target_input === targetInput
        )) {
          return edge;
        }
        changed = true;
        return {
          ...edge,
          targetHandle: targetInput,
          data: { ...edge.data, target_input: targetInput },
        };
      });
      return changed ? nextEdges : currentEdges;
    });
  }, [modules, nodes, setEdges]);

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
      const nodeType = MODULE_NODE_TYPES[moduleType] ?? 'generic_module';
      const definition = modules.find((module) => module.type === moduleType);
      return {
        id: nodeId,
        type: nodeType,
        position,
        data: decorateNodeData(nodeId, nodeType, {
          moduleType,
          config: moduleConfigDefaults(definition),
          values: moduleInputDefaults(definition),
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

  const exportGraph = useCallback((): WorkflowGraph => ({
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
      const savedQuery = graph.nodes.find(
        (workflowNode) => workflowNode.module_type === 'query_input'
      )?.values?.query;
      setQueryText(typeof savedQuery === 'string' ? savedQuery : '');

      stoppedNodeIdsRef.current = new Set(
        graph.nodes
          .filter((workflowNode) => workflowNode.ui?.execution_stopped === true)
          .map((workflowNode) => workflowNode.id)
      );

      setNodes(
        graph.nodes.map((workflowNode) => {
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
        })
      );
      setEdges(
        graph.edges.map((workflowEdge): Edge => {
          const targetNode = graph.nodes.find((node) => node.id === workflowEdge.target);
          const targetDefinition = modules.find(
            (module) => module.type === targetNode?.module_type
          );
          const sourceNode = graph.nodes.find((node) => node.id === workflowEdge.source);
          const sourceDefinition = modules.find(
            (module) => module.type === sourceNode?.module_type
          );
          const targetHandle = resolveTargetInput(
            targetDefinition,
            workflowEdge.target_input,
          ) ?? 'in';
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
      viewportRef.current = graph.viewport;
      setViewport(graph.viewport);
      window.requestAnimationFrame(() => {
        void instanceRef.current?.setViewport(graph.viewport);
        graph.nodes.forEach((workflowNode) => updateNodeInternals(workflowNode.id));
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
              executionConfig: state.config_payload,
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

  const restoreRuntimeInputs = useCallback((run: WorkflowRun) => {
    const query = runtimeQueryFromRun(run);
    if (query !== undefined) setQueryText(query);
  }, [setQueryText]);

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
    onReadOnlyNodesChange,
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
    restoreRuntimeInputs,
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
