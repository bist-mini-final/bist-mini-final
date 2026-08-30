import { useCallback, type Dispatch, type SetStateAction } from 'react';
import { useUpdateNodeInternals, type Edge, type Node } from '@xyflow/react';
import { numericRecord, objectConfig } from '../domain/moduleDefaults';

interface PipelineNodeActionsOptions {
  readonly setNodes: Dispatch<SetStateAction<Node[]>>;
  readonly setEdges: Dispatch<SetStateAction<Edge[]>>;
  readonly updateNodeInternals: ReturnType<typeof useUpdateNodeInternals>;
}

/** Owns node mutations independently from graph connection and runtime projection logic. */
export function usePipelineNodeActions({
  setNodes,
  setEdges,
  updateNodeInternals,
}: PipelineNodeActionsOptions) {
  const updateNodeConfig = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      setNodes((nodes) => nodes.map((node) => node.id === nodeId
        ? { ...node, data: { ...node.data, config: { ...objectConfig(node.data.config), ...patch } } }
        : node));
    },
    [setNodes],
  );

  const updateNodeValues = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      setNodes((nodes) => nodes.map((node) => node.id === nodeId
        ? { ...node, data: { ...node.data, values: { ...objectConfig(node.data.values), ...patch } } }
        : node));
    },
    [setNodes],
  );

  const updateNodeWidth = useCallback((nodeId: string, width: number) => {
    setNodes((nodes) => nodes.map((node) => node.id === nodeId
      ? { ...node, data: { ...node.data, nodeWidth: width } }
      : node));
    window.requestAnimationFrame(() => updateNodeInternals(nodeId));
  }, [setNodes, updateNodeInternals]);

  const updateNodeHeight = useCallback((nodeId: string, height: number) => {
    setNodes((nodes) => nodes.map((node) => node.id === nodeId
      ? { ...node, data: { ...node.data, nodeHeight: height } }
      : node));
    window.requestAnimationFrame(() => updateNodeInternals(nodeId));
  }, [setNodes, updateNodeInternals]);

  const updateNodeColumnWidth = useCallback(
    (nodeId: string, column: string, width: number) => {
      setNodes((nodes) => nodes.map((node) => node.id === nodeId
        ? {
            ...node,
            data: {
              ...node.data,
              columnWidths: { ...numericRecord(node.data.columnWidths), [column]: width },
            },
          }
        : node));
    },
    [setNodes],
  );

  const clearGraph = useCallback(() => {
    setNodes([]);
    setEdges([]);
  }, [setEdges, setNodes]);

  const selectNode = useCallback((nodeId: string) => {
    setNodes((nodes) => nodes.map((node) => ({
      ...node,
      selected: node.id === nodeId,
    })));
  }, [setNodes]);

  const duplicateNode = useCallback((nodeId: string) => {
    setNodes((nodes) => {
      const original = nodes.find((node) => node.id === nodeId);
      if (!original) return nodes;
      const clone: Node = {
        ...original,
        id: `node-${Date.now()}`,
        position: { x: original.position.x + 36, y: original.position.y + 36 },
        data: {
          ...original.data,
          executionState: undefined,
          executionOutput: null,
          executionError: null,
        },
        selected: true,
      };
      return nodes.map((node): Node => ({ ...node, selected: false })).concat(clone);
    });
  }, [setNodes]);

  const deleteNode = useCallback((nodeId: string) => {
    setEdges((edges) => edges.filter(
      (edge) => edge.source !== nodeId && edge.target !== nodeId,
    ));
    setNodes((nodes) => nodes.filter((node) => node.id !== nodeId));
  }, [setEdges, setNodes]);

  return {
    updateNodeConfig,
    updateNodeValues,
    updateNodeWidth,
    updateNodeHeight,
    updateNodeColumnWidth,
    clearGraph,
    selectNode,
    duplicateNode,
    deleteNode,
  };
}
