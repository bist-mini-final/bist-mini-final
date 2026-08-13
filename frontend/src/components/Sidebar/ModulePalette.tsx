import type { CSSProperties, DragEvent, KeyboardEvent, PointerEvent } from 'react';
import {
  Cpu,
  CloudCog,
  Eye,
  FileCode,
  FileSpreadsheet,
  FolderArchive,
  GitBranch,
  GripVertical,
  Layers,
  ListFilter,
  Maximize2,
  Merge,
  MessageSquare,
  Plus,
  Rows3,
  Route,
  Search,
  SearchCheck,
  ScanSearch,
  ScanText,
  Shuffle,
  Sparkles,
  TableProperties,
  X,
  type LucideIcon,
} from 'lucide-react';
import { MODULE_CATEGORIES, MODULE_PRESENTATION } from '../../config/modules';
import type { ModuleDefinition, ModuleType } from '../../types';
import { MODULE_PANEL_MAX_WIDTH, MODULE_PANEL_MIN_WIDTH } from '../../hooks/useResizablePanel';

const ICONS: Record<string, LucideIcon> = {
  Shuffle,
  MessageSquare,
  GitBranch,
  Cpu,
  CloudCog,
  ListFilter,
  Search,
  SearchCheck,
  Merge,
  Maximize2,
  Sparkles,
  FileCode,
  Eye,
  FileSpreadsheet,
  ScanSearch,
  ScanText,
  TableProperties,
  Rows3,
  Route,
  FolderArchive,
};

interface ModulePaletteProps {
  modules: ModuleDefinition[];
  isOpen: boolean;
  onClose?: () => void;
  onAddNode: (type: ModuleType) => void;
  width: number;
  onResizeStart: (event: PointerEvent<HTMLDivElement>) => void;
  onResizeBy: (delta: number) => void;
}

type AccentStyle = CSSProperties & { '--module-accent': string };
type PaletteStyle = CSSProperties & { '--module-palette-width': string };

export function ModulePalette({
  modules,
  isOpen,
  onClose,
  onAddNode,
  width,
  onResizeStart,
  onResizeBy,
}: ModulePaletteProps) {
  const onDragStart = (event: DragEvent, nodeType: ModuleType) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  const handleResizeKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    onResizeBy(event.key === 'ArrowLeft' ? -16 : 16);
  };
  const paletteStyle: PaletteStyle = { '--module-palette-width': `${width}px` };

  return (
    <aside
      className="module-palette"
      data-open={isOpen}
      aria-label="모듈 라이브러리"
      aria-hidden={!isOpen}
      style={paletteStyle}
    >
      <div className="module-palette__surface">
      <div className="module-palette__header">
        <div>
          <h2>Module Library</h2>
          <p>클릭하거나 캔버스로 드래그하세요</p>
        </div>
        <span className="module-count">{modules.length}</span>
        <button
          className="module-palette__close"
          onClick={onClose}
          aria-label="모듈 패널 닫기"
          title="패널 닫기"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="module-palette__list">
        {MODULE_CATEGORIES.map((category) => {
          const categoryModules = modules.filter((module) => module.category === category);
          return (
            <section key={category} className="module-group">
              <h3>{category} Modules</h3>
              <div className="module-group__items">
                {categoryModules.map((module) => {
                  const presentation = MODULE_PRESENTATION[module.type];
                  const Icon = ICONS[presentation.icon] ?? Layers;
                  const style: AccentStyle = { '--module-accent': presentation.color };
                  return (
                    <button
                      key={module.type}
                      type="button"
                      draggable
                      onDragStart={(event) => onDragStart(event, module.type)}
                      onClick={() => onAddNode(module.type)}
                      className="module-card"
                      style={style}
                      title={`Input: ${module.inputs.join(', ') || '없음'}\nOutput: ${module.outputs.join(', ') || '없음'}`}
                      aria-label={`${module.label} 모듈 추가`}
                    >
                      <GripVertical className="module-card__grip" aria-hidden="true" />
                      <span className="module-card__icon"><Icon className="h-4 w-4" /></span>
                      <span className="module-card__content">
                        <strong>{module.label}</strong>
                        <small>{module.description}</small>
                      </span>
                      <span className="module-card__add" aria-hidden="true"><Plus className="h-3 w-3" /></span>
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
      </div>
      {isOpen && (
        <div
          className="module-palette__resize-handle"
          role="separator"
          aria-label="모듈 패널 너비 조절"
          aria-orientation="vertical"
          aria-valuemin={MODULE_PANEL_MIN_WIDTH}
          aria-valuemax={MODULE_PANEL_MAX_WIDTH}
          aria-valuenow={Math.round(width)}
          tabIndex={0}
          onPointerDown={onResizeStart}
          onKeyDown={handleResizeKeyDown}
          title="드래그하여 패널 너비 조절"
        />
      )}
    </aside>
  );
}
