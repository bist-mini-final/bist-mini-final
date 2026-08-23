import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Layers3, Link2, Pencil, Plus, Trash2 } from 'lucide-react';
import type { Edge, Node } from '@xyflow/react';
import type { ModuleDefinition } from '../types';
import type { WorkflowOption } from './Header';
import { NODE_MODULE_TYPES } from '../config/pipeline';

interface Props {
  nodes: Node[];
  edges: Edge[];
  modules: ModuleDefinition[];
  workflows: WorkflowOption[];
  activeWorkflowId: string;
  onSelectWorkflow: (id: string) => void;
  onCreateWorkflow: () => void;
  onDuplicateWorkflow: () => void;
  onRenameWorkflow: () => void;
  onDeleteWorkflow: () => void;
  onSelectNode: (nodeId: string) => void;
  onDuplicateNode: (nodeId: string) => void;
  readOnly: boolean;
}

export function WorkflowLayersPanel(props: Props) {
  const [open, setOpen] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(props.activeWorkflowId);
  const labels = useMemo(() => new Map(props.modules.map((item) => [item.type, item.label])), [props.modules]);
  const active = props.workflows.find((item) => item.id === props.activeWorkflowId);
  return <aside className="workflow-layers" aria-label="워크플로와 레이어">
    <div className="workflow-layers__toolbar">
      <button className="workflow-layers__header" onClick={() => setOpen((value) => !value)}><Layers3 size={16} /> 워크플로 <small>{props.workflows.length}</small>{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</button>
      <button className="workflow-layers__create" onClick={props.onCreateWorkflow} title="새 워크플로"><Plus size={16} /></button>
    </div>
    {open && <div className="workflow-layers__body">
      {props.workflows.map((flow) => {
        const isActive = flow.id === props.activeWorkflowId;
        const isExpanded = expanded === flow.id;
        const isCanonical = flow.id === 'rag_query' || flow.id === 'excel_ingestion';
        return <section key={flow.id} className={`workflow-layers__frame${isActive ? ' workflow-layers__frame--active' : ''}`}>
          <div className="workflow-layers__frame-row">
            <button className="workflow-layers__frame-toggle" onClick={() => { setExpanded(isExpanded ? null : flow.id); if (!isActive) props.onSelectWorkflow(flow.id); }}><span>{isExpanded ? '▾' : '▸'}</span>{flow.name}</button>
            {isActive && <div className="workflow-layers__actions"><button onClick={props.onDuplicateWorkflow} title="워크플로 복제"><Copy size={13} /></button><button onClick={props.onRenameWorkflow} title="이름 변경" disabled={isCanonical}><Pencil size={13} /></button><button onClick={props.onDeleteWorkflow} title="삭제" disabled={isCanonical}><Trash2 size={13} /></button></div>}
          </div>
          {isActive && isExpanded && <div className="workflow-layers__nodes">
            <small>{props.nodes.length} layers · {props.edges.length} connections</small>
            {props.nodes.map((node, index) => {
              const type = NODE_MODULE_TYPES[node.type ?? ''];
              const name = labels.get(type) ?? type ?? 'Unknown node';
              const inCount = props.edges.filter((edge) => edge.target === node.id).length;
              const outCount = props.edges.filter((edge) => edge.source === node.id).length;
              return <div className={`workflow-layer${node.selected ? ' workflow-layer--selected' : ''}`} key={node.id}><button className="workflow-layer__select" onClick={() => props.onSelectNode(node.id)}><span>{index + 1}</span><b>{name}</b><em><Link2 size={11} />{inCount}/{outCount}</em></button><button className="workflow-layer__copy" onClick={() => props.onDuplicateNode(node.id)} title="레이어 복제" disabled={props.readOnly}><Copy size={12} /></button></div>;
            })}
          </div>}
          {!isActive && isExpanded && <div className="workflow-layers__hint">클릭하면 이 워크플로를 엽니다.</div>}
        </section>;
      })}
      {!active && <div className="workflow-layers__hint">워크플로를 불러오는 중…</div>}
    </div>}
  </aside>;
}
