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
import { summarizeDag } from '../domain/graph';
import {
  moduleConfigDefaults,
  moduleInputDefaults,
  objectConfig,
  resolveTargetInput,
} from '../domain/moduleDefaults';
import {
  BRANCH_COLORS,
  EXECUTION_BRANCHES,
  restorePipelineEdges,
  restorePipelineNodes,
  serializePipelineGraph,
} from '../domain/pipelineGraphPersistence';
import { usePipelineNodeActions } from './usePipelineNodeActions';
import { usePipelineRuntimeProjection } from './usePipelineRuntimeProjection';
import type {
  ModuleDefinition,
  ModuleType,
  WorkflowGraph,
  WorkflowViewport,
} from '../types';

interface PipelineGraphOptions {
  queryText: string;
  setQueryText: (text: string) => void;
  activeStep: number;
  modules: ModuleDefinition[];
}

const DEFAULT_VIEWPORT: WorkflowViewport = { x: 0, y: 0, zoom: 1 };
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

  const {
    updateNodeConfig,
    updateNodeValues,
    updateNodeWidth,
    updateNodeHeight,
    updateNodeColumnWidth,
    clearGraph,
    selectNode,
    duplicateNode,
    deleteNode,
  } = usePipelineNodeActions({ setNodes, setEdges, updateNodeInternals });

  const {
    applyRun,
    restoreRuntimeInputs,
    clearExecutionState,
    clearNodeExecutionState,
    resumeNodeExecution,
  } = usePipelineRuntimeProjection({
    edges,
    setNodes,
    setEdges,
    setQueryText,
    stoppedNodeIdsRef,
  });

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

  const nodeIdSignature = nodes.map((node) => node.id).join('\u0000');

  useEffect(() => {
    if (modules.length === 0) return;
    const nodeIds = nodeIdSignature ? nodeIdSignature.split('\u0000') : [];
    const frame = window.requestAnimationFrame(() => {
      nodeIds.forEach((nodeId) => updateNodeInternals(nodeId));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [modules, nodeIdSignature, updateNodeInternals]);

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

  const exportGraph = useCallback(
    (): WorkflowGraph => serializePipelineGraph(nodes, edges, viewportRef.current),
    [edges, nodes],
  );

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

      setNodes(restorePipelineNodes(graph, decorateNodeData));
      setEdges(restorePipelineEdges(graph, modules));
      viewportRef.current = graph.viewport;
      setViewport(graph.viewport);
      window.requestAnimationFrame(() => {
        void instanceRef.current?.setViewport(graph.viewport);
        graph.nodes.forEach((workflowNode) => updateNodeInternals(workflowNode.id));
      });
    },
    [decorateNodeData, modules, setEdges, setNodes, setQueryText, updateNodeInternals]
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
