import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Layers3, Link2, Pencil, Plus, Trash2 } from 'lucide-react';
import type { Edge, Node } from '@xyflow/react';
import type { ModuleDefinition, OutputBranch, WorkflowDocument, WorkflowGraph } from '../types';
import { NODE_MODULE_TYPES } from '../config/pipeline';
import { pipelineApi } from '../services/api';

interface Props {
  nodes: Node[];
  edges: Edge[];
  modules: ModuleDefinition[];
  onSelect: (nodeId: string) => void;
  onDuplicateNode: (nodeId: string) => void;
  workflowId: string;
  workflowName: string;
  onSwitchWorkflow: (workflowId: string, workflowName?: string) => Promise<void>;
}

type Layer = { node: Node; depth: number; incoming: number; outgoing: number };

function makeLayers(nodes: Node[], edges: Edge[]): Layer[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const incoming = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(nodes.map((node) => [node.id, 0]));
  const children = new Map(nodes.map((node) => [node.id, [] as string[]]));
  for (const edge of edges) {
    if (!byId.has(edge.source) || !byId.has(edge.target)) continue;
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
    outgoing.set(edge.source, (outgoing.get(edge.source) ?? 0) + 1);
    children.get(edge.source)?.push(edge.target);
  }
  const queue = nodes.filter((node) => incoming.get(node.id) === 0).map((node) => node.id);
  const depth = new Map(nodes.map((node) => [node.id, 0]));
  const ordered: string[] = [];
  const remaining = new Map(incoming);
  while (queue.length) {
    const nodeId = queue.shift()!;
    ordered.push(nodeId);
    for (const child of children.get(nodeId) ?? []) {
      depth.set(child, Math.max(depth.get(child) ?? 0, (depth.get(nodeId) ?? 0) + 1));
      const next = (remaining.get(child) ?? 1) - 1;
      remaining.set(child, next);
      if (next === 0) queue.push(child);
    }
  }
  // Still show invalid/cyclic nodes rather than hiding them from the layer list.
  for (const node of nodes) if (!ordered.includes(node.id)) ordered.push(node.id);
  return ordered.map((nodeId) => ({ node: byId.get(nodeId)!, depth: depth.get(nodeId) ?? 0, incoming: incoming.get(nodeId) ?? 0, outgoing: outgoing.get(nodeId) ?? 0 }));
}

export function WorkflowLayersPanel({ nodes, edges, modules, onSelect, onDuplicateNode, workflowId, workflowName, onSwitchWorkflow }: Props) {
  const [open, setOpen] = useState(true);
  const [workflows, setWorkflows] = useState<WorkflowDocument[]>([]);
  const layers = useMemo(() => makeLayers(nodes, edges), [nodes, edges]);
  const labels = useMemo(() => new Map(modules.map((item) => [item.type, item.label])), [modules]);
  useEffect(() => { void pipelineApi.getWorkflows().then(({ workflows: items }) => setWorkflows(items)).catch(() => undefined); }, [workflowId]);
  const createWorkflow = async () => {
    const name = window.prompt('새 워크플로 이름', '새 RAG 워크플로');
    if (!name?.trim()) return;
    const id = `workflow-${Date.now()}`;
    const graph: WorkflowGraph = { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } };
    await pipelineApi.saveWorkflow(id, name.trim(), graph);
    setWorkflows((current) => [...current, { schema_version: 1, id, name: name.trim(), updated_at: new Date().toISOString(), graph }]);
    await onSwitchWorkflow(id, name.trim());
  };
  const duplicateWorkflow = async (flow: WorkflowDocument) => {
    const name = window.prompt('복제할 워크플로 이름', `${flow.name} 복사본`);
    if (!name?.trim()) return;
    const id = `workflow-${Date.now()}`;
    const graph = structuredClone(flow.graph);
    await pipelineApi.saveWorkflow(id, name.trim(), graph);
    const copy = { ...flow, id, name: name.trim(), updated_at: new Date().toISOString(), graph };
    setWorkflows((current) => [...current, copy]);
    await onSwitchWorkflow(id, copy.name);
  };
  const renameWorkflow = async (flow: WorkflowDocument) => {
    const name = window.prompt('워크플로 이름 변경', flow.name);
    if (!name?.trim() || name.trim() === flow.name) return;
    await pipelineApi.saveWorkflow(flow.id, name.trim(), flow.graph);
    setWorkflows((current) => current.map((item) => item.id === flow.id ? { ...item, name: name.trim() } : item));
    if (flow.id === workflowId) await onSwitchWorkflow(flow.id, name.trim());
  };
  const deleteWorkflow = async (flow: WorkflowDocument) => {
    if (flow.id === 'workflow') { window.alert('기본 워크플로는 삭제할 수 없습니다.'); return; }
    if (!window.confirm(`'${flow.name}' 워크플로를 삭제할까요?`)) return;
    await pipelineApi.deleteWorkflow(flow.id);
    setWorkflows((current) => current.filter((item) => item.id !== flow.id));
    if (flow.id === workflowId) await onSwitchWorkflow('workflow', 'Excel RAG Flow');
  };
  const frames = workflows.map((flow) => flow.id === workflowId
    ? { ...flow, name: workflowName, graph: { ...flow.graph, nodes: nodes.map((node) => ({ id: node.id, module_type: NODE_MODULE_TYPES[node.type ?? ''] ?? 'query_input', position: node.position, config: (node.data.config as Record<string, unknown>) ?? {} })), edges: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, source_output: edge.data?.source_output as string | undefined, target_input: edge.data?.target_input as string | undefined, source_branch: edge.data?.source_branch as OutputBranch | undefined })) } }
    : flow);
  return <aside className={`workflow-layers${open ? '' : ' workflow-layers--closed'}`} aria-label="현재 워크플로 레이어">
    <div className="workflow-layers__toolbar">
      <button className="workflow-layers__header" onClick={() => setOpen((value) => !value)}>
        <Layers3 size={16} /> <span>워크플로</span><small>{frames.length}</small>{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
      </button>
      <button className="workflow-layers__create" onClick={() => void createWorkflow()} aria-label="새 워크플로 만들기" title="새 워크플로 만들기"><Plus size={16} /></button>
    </div>
    {open && <div className="workflow-layers__body">
      {frames.map((flow) => <details key={flow.id} className="workflow-layers__frame" open={flow.id === workflowId}>
        <summary onClick={(event) => { if (flow.id !== workflowId) { event.preventDefault(); void onSwitchWorkflow(flow.id, flow.name); } }}><span>{flow.name}</span><small>{flow.graph.nodes.length} layers</small><div className="workflow-layers__actions"><button onClick={(event) => { event.preventDefault(); event.stopPropagation(); void duplicateWorkflow(flow); }} title="워크플로 복제"><Copy size={13} /></button><button onClick={(event) => { event.preventDefault(); event.stopPropagation(); void renameWorkflow(flow); }} title="이름 변경"><Pencil size={13} /></button><button onClick={(event) => { event.preventDefault(); event.stopPropagation(); void deleteWorkflow(flow); }} title="삭제" disabled={flow.id === 'workflow'}><Trash2 size={13} /></button></div></summary>
        {flow.id === workflowId && layers.map(({ node, depth, incoming, outgoing }, index) => {
        const moduleType = NODE_MODULE_TYPES[node.type ?? ''];
        const title = labels.get(moduleType) ?? moduleType ?? node.type ?? 'Unknown node';
        const status = typeof node.data.executionState === 'string' ? node.data.executionState : 'idle';
        return <div key={node.id} className={`workflow-layer workflow-layer--${status}${node.selected ? ' workflow-layer--selected' : ''}`} style={{ paddingLeft: `${12 + Math.min(depth, 4) * 15}px` }} title={node.id}>
          <button className="workflow-layer__select" onClick={() => onSelect(node.id)}>
          <span className="workflow-layer__index">{index + 1}</span><span className="workflow-layer__name">{title}</span>
          <span className="workflow-layer__links"><Link2 size={11} />{incoming}/{outgoing}</span>
          </button><button className="workflow-layer__copy" onClick={() => onDuplicateNode(node.id)} title="레이어 복제" aria-label={`${title} 레이어 복제`}><Copy size={12} /></button>
        </div>;
        })}
      </details>)}
    </div>}
  </aside>;
}
