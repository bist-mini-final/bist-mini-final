import { useEffect, useMemo } from 'react';
import { LayoutTemplate, Plus, X } from 'lucide-react';
import type { ModuleDefinition } from '../types';
import type { WorkflowOption } from './Header';
import { Button, IconButton } from '../../../shared/ui';
import './WorkflowTemplatePanel.css';

interface WorkflowTemplatePanelProps {
  isOpen: boolean;
  isLoading: boolean;
  workflows: WorkflowOption[];
  modules: ModuleDefinition[];
  onClose: () => void;
  onCreateFromTemplate: (templateId: string) => void;
}

export function WorkflowTemplatePanel({
  isOpen,
  isLoading,
  workflows,
  modules,
  onClose,
  onCreateFromTemplate,
}: WorkflowTemplatePanelProps) {
  const templates = useMemo(
    () => workflows.filter((workflow) => workflow.template),
    [workflows],
  );
  const labels = useMemo(
    () => new Map(modules.map((module) => [module.type, module.label])),
    [modules],
  );

  useEffect(() => {
    if (!isOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="workflow-template-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="workflow-template-panel"
        role="dialog"
        aria-modal="true"
        aria-label="새 워크플로 만들기"
      >
        <header className="workflow-template-panel__header">
          <span><Plus size={18} /> 새 워크플로 만들기</span>
          <IconButton size="sm" variant="ghost" onClick={onClose} aria-label="새 워크플로 만들기 닫기">
            <X size={18} />
          </IconButton>
        </header>
        <p className="workflow-template-panel__intro">
          표준 파이프라인을 복사해 모듈과 연결을 자유롭게 수정할 수 있습니다.
        </p>
        <div className="workflow-template-panel__section-heading">
          <strong>표준 워크플로에서 시작</strong>
          <span>읽기 전용 원본은 그대로 유지됩니다.</span>
        </div>
        {isLoading && (
          <p className="workflow-template-panel__state">템플릿을 불러오는 중…</p>
        )}
        {!isLoading && templates.length === 0 && (
          <p className="workflow-template-panel__state">사용 가능한 템플릿이 없습니다.</p>
        )}
        <div className="workflow-template-panel__list">
          {templates.map((template) => (
            <article key={template.id} className="workflow-template-panel__card">
              <div className="workflow-template-panel__card-title">
                <LayoutTemplate size={19} />
                <span>
                  <strong>{template.name}</strong>
                  <small>{template.nodeCount} nodes · {template.edgeCount} connections</small>
                </span>
                <em>읽기 전용 원본</em>
              </div>
              <p>
                {template.moduleTypes
                  .map((type) => labels.get(type) ?? type)
                  .join(' → ')}
              </p>
              <Button
                variant="primary"
                className="workflow-template-panel__create"
                type="button"
                onClick={() => {
                  onCreateFromTemplate(template.id);
                  onClose();
                }}
              >
                편집 가능한 사본 만들기
              </Button>
            </article>
          ))}
        </div>
      </aside>
    </div>
  );
}
