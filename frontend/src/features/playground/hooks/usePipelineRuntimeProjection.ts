import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import type { Edge, Node } from '@xyflow/react';
import { collectDescendantNodeIds } from '../domain/graph';
import { runtimeQueryFromRun } from '../domain/execution';
import {
  applyWorkflowRunToEdges,
  applyWorkflowRunToNodes,
  clearWorkflowExecutionEdges,
  clearWorkflowExecutionNodes,
  deactivateConnectedEdges,
  resumeWorkflowExecutionNodes,
  stopWorkflowExecutionNodes,
} from '../domain/pipelineGraphRuntime';
import type { WorkflowRun } from '../types';

interface RuntimeProjectionOptions {
  readonly edges: Edge[];
  readonly setNodes: Dispatch<SetStateAction<Node[]>>;
  readonly setEdges: Dispatch<SetStateAction<Edge[]>>;
  readonly setQueryText: (query: string) => void;
  readonly stoppedNodeIdsRef: MutableRefObject<Set<string>>;
}

/** Projects persisted run state onto React Flow without owning graph editing. */
export function usePipelineRuntimeProjection({
  edges,
  setNodes,
  setEdges,
  setQueryText,
  stoppedNodeIdsRef,
}: RuntimeProjectionOptions) {
  const applyRun = useCallback((run: WorkflowRun) => {
    const stoppedNodeIds = stoppedNodeIdsRef.current;
    setNodes((nodes) => applyWorkflowRunToNodes(nodes, run, stoppedNodeIds));
    setEdges((currentEdges) => applyWorkflowRunToEdges(currentEdges, run, stoppedNodeIds));
  }, [setEdges, setNodes, stoppedNodeIdsRef]);

  const restoreRuntimeInputs = useCallback((run: WorkflowRun) => {
    const query = runtimeQueryFromRun(run);
    if (query !== undefined) setQueryText(query);
  }, [setQueryText]);

  const clearExecutionState = useCallback(() => {
    stoppedNodeIdsRef.current = new Set();
    setNodes(clearWorkflowExecutionNodes);
    setEdges(clearWorkflowExecutionEdges);
  }, [setEdges, setNodes, stoppedNodeIdsRef]);

  const clearNodeExecutionState = useCallback((nodeId: string) => {
    const resetNodeIds = collectDescendantNodeIds(nodeId, edges);
    stoppedNodeIdsRef.current = new Set([...stoppedNodeIdsRef.current, ...resetNodeIds]);
    setNodes((nodes) => stopWorkflowExecutionNodes(nodes, resetNodeIds));
    setEdges((currentEdges) => deactivateConnectedEdges(currentEdges, resetNodeIds));
  }, [edges, setEdges, setNodes, stoppedNodeIdsRef]);

  const resumeNodeExecution = useCallback((nodeId: string) => {
    const resumedNodeIds = collectDescendantNodeIds(nodeId, edges);
    stoppedNodeIdsRef.current = new Set(
      [...stoppedNodeIdsRef.current].filter((stoppedId) => !resumedNodeIds.has(stoppedId)),
    );
    setNodes((nodes) => resumeWorkflowExecutionNodes(nodes, resumedNodeIds));
  }, [edges, setNodes, stoppedNodeIdsRef]);

  return {
    applyRun,
    restoreRuntimeInputs,
    clearExecutionState,
    clearNodeExecutionState,
    resumeNodeExecution,
  };
}
