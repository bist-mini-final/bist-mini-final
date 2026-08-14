import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
} from 'react';
import { Handle, Position, useNodeId, useReactFlow } from '@xyflow/react';
import { Play, Settings2, Square, Trash2, Clock, Coins, type LucideIcon } from 'lucide-react';
import { useOpenModuleSettings } from '../../contexts/ModuleSettingsContext';
import { useModuleExecution } from '../../contexts/ModuleExecutionContext';

type NodeState = 'idle' | 'active' | 'done' | 'failed' | 'skipped';

interface NodeShellProps {
  accent: string;
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  children?: ReactNode;
  state?: NodeState;
  selected?: boolean;
  width?: number;
  height?: number;
  hasInput?: boolean;
  inputPorts?: string[];
  hasOutput?: boolean;
  outputBranches?: string[];
  headerAccessory?: ReactNode;
  headerActions?: ReactNode;
  bodyClassName?: string;
  onWidthChange?: (width: number) => void;
  onHeightChange?: (height: number) => void;
  minWidth?: number;
  maxWidth?: number;
  minHeight?: number;
  maxHeight?: number;
  nodeData?: Record<string, unknown>;
}

type NodeStyle = CSSProperties & {
  '--node-accent': string;
  '--node-width': string;
};

export function NodeShell({
  accent,
  icon: Icon,
  eyebrow,
  title,
  children,
  state = 'idle',
  selected = false,
  width = 320,
  height,
  hasInput = true,
  inputPorts = [],
  hasOutput = true,
  outputBranches = [],
  headerAccessory,
  headerActions,
  bodyClassName = '',
  onWidthChange,
  onHeightChange,
  minWidth = 320,
  maxWidth = 1200,
  minHeight = 280,
  maxHeight = 1600,
  nodeData: propNodeData,
}: NodeShellProps) {
  const nodeId = useNodeId();
  const { deleteElements, getEdges, getNodes } = useReactFlow();
  const openModuleSettings = useOpenModuleSettings();
  const {
    onExecuteNode,
    onStopExecution,
    onClearNodeResult,
    isExecuting,
  } = useModuleExecution();
  const isStopMode = state === 'active' || state === 'done' || state === 'failed';
  const resizeCleanupRef = useRef<(() => void) | null>(null);

  const clampWidth = useCallback(
    (nextWidth: number) => Math.min(maxWidth, Math.max(minWidth, Math.round(nextWidth))),
    [maxWidth, minWidth]
  );
  const clampHeight = useCallback(
    (nextHeight: number) => Math.min(maxHeight, Math.max(minHeight, Math.round(nextHeight))),
    [maxHeight, minHeight]
  );

  const stopResize = useCallback(() => {
    resizeCleanupRef.current?.();
    resizeCleanupRef.current = null;
  }, []);

  useEffect(() => stopResize, [stopResize]);

  const startResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!onWidthChange) return;
    event.preventDefault();
    event.stopPropagation();
    stopResize();
    const startX = event.clientX;
    const startWidth = width;
    const handlePointerMove = (moveEvent: PointerEvent) => {
      onWidthChange(clampWidth(startWidth + moveEvent.clientX - startX));
    };
    const handlePointerUp = () => stopResize();
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
    resizeCleanupRef.current = () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
    };
  }, [clampWidth, onWidthChange, stopResize, width]);

  const resizeWithKeyboard = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!onWidthChange || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    onWidthChange(clampWidth(width + (event.key === 'ArrowRight' ? 24 : -24)));
  }, [clampWidth, onWidthChange, width]);

  const startHeightResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!onHeightChange || height === undefined) return;
    event.preventDefault();
    event.stopPropagation();
    stopResize();
    const startY = event.clientY;
    const startHeight = height;
    const handlePointerMove = (moveEvent: PointerEvent) => {
      onHeightChange(clampHeight(startHeight + moveEvent.clientY - startY));
    };
    const handlePointerUp = () => stopResize();
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
    resizeCleanupRef.current = () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
    };
  }, [clampHeight, height, onHeightChange, stopResize]);

  const resizeHeightWithKeyboard = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (
      !onHeightChange
      || height === undefined
      || !['ArrowUp', 'ArrowDown'].includes(event.key)
    ) return;
    event.preventDefault();
    event.stopPropagation();
    onHeightChange(clampHeight(height + (event.key === 'ArrowDown' ? 24 : -24)));
  }, [clampHeight, height, onHeightChange]);

  const graphEdges = getEdges();
  const incomingEdges = nodeId
    ? graphEdges.filter((edge) => edge.target === nodeId)
    : [];
  const resolvedInputHandles = inputPorts.length > 0 ? inputPorts : ['in'];
  const connectedOutputHandles = nodeId
    ? graphEdges
        .filter((edge) => edge.source === nodeId && typeof edge.sourceHandle === 'string')
        .map((edge) => edge.sourceHandle as string)
    : [];
  const resolvedOutputHandles = Array.from(
    new Set([...outputBranches, ...connectedOutputHandles])
  );
  const matchesInput = (targetHandle: string | null | undefined, input: string) =>
    targetHandle === input
    || (resolvedInputHandles.length === 1 && targetHandle === 'in');
  const isInputConnected = !hasInput || resolvedInputHandles.every((input) =>
    incomingEdges.some((edge) => matchesInput(edge.targetHandle, input))
  );
  const nodeById = new Map(getNodes().map((node) => [node.id, node]));
  const isInputReady = !hasInput || resolvedInputHandles.every((input) =>
    incomingEdges.some((edge) => {
      if (!matchesInput(edge.targetHandle, input)) return false;
      const sourceData = nodeById.get(edge.source)?.data;
      if (sourceData?.executionState !== 'succeeded') return false;
      const branch = edge.data?.source_branch;
      return typeof branch !== 'string' || sourceData.executionOutcome === branch;
    })
  );
  const isRunDisabled = !isStopMode && (!isInputReady || isExecuting);

  const currentNode = nodeId ? nodeById.get(nodeId) : null;
  const mergedData = { ...(currentNode?.data ?? {}), ...(propNodeData ?? {}) } as Record<string, unknown>;
  const elapsedMs = typeof mergedData.elapsedMs === 'number'
    ? mergedData.elapsedMs
    : typeof mergedData.elapsed_ms === 'number'
      ? mergedData.elapsed_ms
      : null;

  const costUsd = typeof mergedData.costUsd === 'number'
    ? mergedData.costUsd
    : typeof mergedData.cost_usd === 'number'
      ? mergedData.cost_usd
      : null;

  const usage = mergedData.usage as { total_tokens?: number } | undefined;
  const cacheHit = Boolean(mergedData.cacheHit);

  const isRunning = state === 'active';

  // Live elapsed timer: counts up in real-time while node is running
  const [liveMs, setLiveMs] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!isRunning) {
      // Stop timer when no longer running
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setLiveMs(null);
      return;
    }
    // Determine start time from node data
    const startedAtRaw = mergedData.startedAt ?? mergedData.started_at;
    const startTs = typeof startedAtRaw === 'string'
      ? new Date(startedAtRaw).getTime()
      : Date.now();

    const tick = () => setLiveMs(Date.now() - startTs);
    tick(); // immediate first tick
    timerRef.current = setInterval(tick, 100);
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning]);

  // Display: live counter while running, backend value when done
  const displayMs = isRunning ? liveMs : elapsedMs;

  const formattedTime = displayMs !== null
    ? displayMs >= 1000
      ? `${(displayMs / 1000).toFixed(displayMs >= 10000 ? 1 : 2)}s`
      : `${Math.round(displayMs)}ms`
    : null;

  const style: NodeStyle = {
    '--node-accent': accent,
    '--node-width': `${width}px`,
    ...(height === undefined ? {} : { height: `${height}px` }),
  };

  return (
    <section className="flow-node relative" data-state={state} data-selected={selected ? 'true' : 'false'} style={style}>
      {hasInput && resolvedInputHandles.map((input, index, handles) => {
        const top = `${((index + 1) / (handles.length + 1)) * 100}%`;
        return (
          <div key={input} className="flow-node__input-port" style={{ top }}>
            <Handle
              type="target"
              position={Position.Left}
              id={input}
              className="nodrag nopan flow-node__handle"
              isConnectable
              title={`${input} 입력 연결`}
            />
            <span>{input}</span>
          </div>
        );
      })}

      <header className="flow-node__header">
        <div className="flow-node__icon" aria-hidden="true">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flow-node__eyebrow">{eyebrow}</div>
          <div className="flow-node__title">{title}</div>
        </div>
        <div className="flow-node__header-actions">
          {headerAccessory ?? <span className="flow-node__status" aria-hidden="true" />}
          {headerActions}
          <button
            type="button"
            className={`nodrag nopan flow-node__action ${
              isStopMode ? 'flow-node__stop' : 'flow-node__execute'
            } ${
              isRunDisabled ? 'opacity-30 cursor-not-allowed' : ''
            }`}
            disabled={isRunDisabled}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              if (isStopMode) {
                if (state === 'active' && isExecuting) {
                  onStopExecution();
                  if (nodeId) onClearNodeResult(nodeId);
                } else if (nodeId) {
                  onClearNodeResult(nodeId);
                }
                return;
              }
              if (nodeId && isInputReady && !isExecuting) {
                onExecuteNode(nodeId);
              }
            }}
            aria-label={
              isStopMode
                ? state === 'active'
                  ? `${title} 실행 정지`
                  : `${title} 결과 숨기기`
                : `${title} 단독 실행`
            }
            title={
              isStopMode
                ? state === 'active'
                  ? '실행 정지'
                  : '결과 표시 지우기'
                : !isInputConnected
                ? '입력 연결이 필요합니다 (상류 모듈과 선을 연결하세요)'
                : !isInputReady
                  ? '상류 모듈의 실행 결과가 필요합니다'
                : `${title} 단독 실행`
            }
          >
            {isStopMode
              ? <Square className="h-3.5 w-3.5 fill-current" />
              : <Play className="h-3.5 w-3.5 fill-current" />}
          </button>
          <button
            type="button"
            className="nodrag nopan flow-node__action flow-node__settings"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              if (nodeId) openModuleSettings?.(nodeId);
            }}
            aria-label={`${title} 상세 설정`}
            title="입출력 스키마 및 상세 설정"
          >
            <Settings2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="nodrag nopan flow-node__action flow-node__delete"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              if (nodeId) void deleteElements({ nodes: [{ id: nodeId }] });
            }}
            aria-label={`${title} 모듈 삭제`}
            title="모듈 삭제"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {children !== undefined && children !== null && (
        <div className={`flow-node__body ${bodyClassName}`}>{children}</div>
      )}

      {hasOutput && (resolvedOutputHandles.length > 0 ? resolvedOutputHandles : ['out']).map((branch, index, handles) => (
        <Handle
          key={branch}
          type="source"
          position={Position.Right}
          id={branch}
          className={`nodrag nopan flow-node__handle${branch === 'out' ? '' : ' flow-node__branch-handle'}`}
          data-branch={branch === 'out' ? undefined : branch}
          style={{ top: `${((index + 1) / (handles.length + 1)) * 100}%` }}
          isConnectable
          title={branch === 'out' ? '출력 연결' : `${branch} 출력 연결`}
        />
      ))}

      {onWidthChange && (
        <div
          className="nodrag nopan flow-node__resize-handle"
          role="separator"
          aria-label={`${title} 가로 크기 조절`}
          aria-orientation="vertical"
          aria-valuemin={minWidth}
          aria-valuemax={maxWidth}
          aria-valuenow={width}
          tabIndex={0}
          title="드래그하여 모듈 너비 조절"
          onPointerDown={startResize}
          onKeyDown={resizeWithKeyboard}
        />
      )}

      {onHeightChange && height !== undefined && (
        <div
          className="nodrag nopan flow-node__height-resize-handle"
          role="separator"
          aria-label={`${title} 세로 크기 조절`}
          aria-orientation="horizontal"
          aria-valuemin={minHeight}
          aria-valuemax={maxHeight}
          aria-valuenow={height}
          tabIndex={0}
          title="위아래로 드래그하여 모듈 높이 조절"
          onPointerDown={startHeightResize}
          onKeyDown={resizeHeightWithKeyboard}
        />
      )}

      {(isRunning || formattedTime !== null || costUsd !== null) && (
        <div className="absolute -bottom-5 left-0 flex items-center gap-1.5 text-[10px] font-mono pointer-events-none select-none z-10">
          {(isRunning || formattedTime !== null) && (
            <span className="flex items-center gap-1 font-semibold text-slate-500">
              <Clock className={`h-3 w-3 text-emerald-500${isRunning ? ' animate-pulse' : ''}`} />
              {formattedTime ?? '0ms'}
              {!isRunning && cacheHit && <span className="text-[9px] text-emerald-500 font-normal">(캐시)</span>}
            </span>
          )}
          {!isRunning && costUsd !== null && (
            <span className={`flex items-center gap-1 font-semibold text-emerald-600 ${formattedTime !== null ? 'pl-1' : ''}`}>
              <Coins className="h-3 w-3 text-amber-400" />
              ${costUsd < 0.0001 ? '<0.0001' : costUsd.toFixed(4)}
              {usage?.total_tokens ? <span className="text-slate-400 font-normal">({usage.total_tokens.toLocaleString()}t)</span> : null}
            </span>
          )}
        </div>
      )}
    </section>
  );
}

export function getExecutionNodeState(
  executionState: string | undefined
): NodeState {
  if (executionState === 'idle') return 'idle';
  if (executionState === 'failed') return 'failed';
  if (executionState === 'skipped') return 'skipped';
  if (executionState === 'running') return 'active';
  if (executionState === 'succeeded') return 'done';
  return 'idle';
}
