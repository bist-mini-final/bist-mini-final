import React, { useCallback, useEffect, useRef, useState } from 'react';
import { BaseEdge, EdgeProps, getBezierPath, useReactFlow } from '@xyflow/react';

export const CustomEdge: React.FC<EdgeProps> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  data,
  selected,
}) => {
  const { setEdges, screenToFlowPosition } = useReactFlow();
  const [isHovered, setIsHovered] = useState(false);
  const pathRef = useRef<SVGPathElement | null>(null);
  const [handlePos, setHandlePos] = useState<{ x: number; y: number } | null>(null);

  const customControlX = typeof data?.controlX === 'number' ? data.controlX : null;
  const customControlY = typeof data?.controlY === 'number' ? data.controlY : null;
  const hasCustomControl = customControlX !== null && customControlY !== null;

  const [defaultPath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const cx = hasCustomControl ? customControlX : 0;
  const cy = hasCustomControl ? customControlY : 0;

  const edgePath = hasCustomControl
    ? `M ${sourceX} ${sourceY} Q ${cx} ${cy} ${targetX} ${targetY}`
    : defaultPath;

  // Use SVG getPointAtLength to find exact midpoint on the rendered path
  useEffect(() => {
    const el = pathRef.current;
    if (!el) { setHandlePos(null); return; }
    try {
      const len = el.getTotalLength();
      if (len === 0) { setHandlePos(null); return; }
      const pt = el.getPointAtLength(len / 2);
      setHandlePos({ x: pt.x, y: pt.y });
    } catch {
      setHandlePos(null);
    }
  }, [edgePath]);

  const isActive = Boolean(data?.active);
  const isDone = Boolean(data?.done);
  const color = (data?.color as string) || '#10b981';

  const onControlPointerDown = useCallback(
    (event: React.PointerEvent) => {
      event.stopPropagation();
      const el = event.currentTarget as HTMLElement;
      try { el.setPointerCapture(event.pointerId); } catch {}

      const onMove = (e: PointerEvent) => {
        const fp = screenToFlowPosition({ x: e.clientX, y: e.clientY });
        const newCx = Math.round(2 * fp.x - 0.5 * sourceX - 0.5 * targetX);
        const newCy = Math.round(2 * fp.y - 0.5 * sourceY - 0.5 * targetY);
        setEdges((edges) =>
          edges.map((edge) =>
            edge.id === id
              ? { ...edge, data: { ...edge.data, controlX: newCx, controlY: newCy } }
              : edge
          )
        );
      };

      const onUp = (e: PointerEvent) => {
        try { el.releasePointerCapture(e.pointerId); } catch {}
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
        window.removeEventListener('pointercancel', onUp);
      };

      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
      window.addEventListener('pointercancel', onUp);
    },
    [id, sourceX, sourceY, targetX, targetY, setEdges, screenToFlowPosition]
  );

  const onControlDoubleClick = useCallback(
    (event: React.MouseEvent) => {
      event.stopPropagation();
      setEdges((edges) =>
        edges.map((e) => {
          if (e.id !== id) return e;
          const d = { ...e.data };
          delete d.controlX;
          delete d.controlY;
          return { ...e, data: d };
        })
      );
    },
    [id, setEdges]
  );

  const isSelectedOrHovered = Boolean(selected || isHovered);

  const selectEdge = useCallback(
    (event: React.MouseEvent<SVGPathElement>) => {
      event.stopPropagation();
      setEdges((edges) => edges.map((edge) => ({
        ...edge,
        selected: event.shiftKey ? (edge.id === id ? !edge.selected : edge.selected) : edge.id === id,
      })));
    },
    [id, setEdges]
  );

  const openContextDelete = useCallback(
    (event: React.MouseEvent<SVGPathElement>) => {
      event.preventDefault();
      selectEdge(event);
    },
    [selectEdge]
  );

  return (
    <g
      className="workflow-edge"
      data-execution-state={isActive ? 'active' : isDone ? 'done' : 'idle'}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/*
        Hidden measurement path with the same 'd' as the rendered edge.
        getPointAtLength reads its DOM geometry to get the exact midpoint.
      */}
      <path
        ref={pathRef}
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={1}
        style={{ pointerEvents: 'none', visibility: 'hidden' }}
      />

      {/* Wide invisible hit area */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={24}
        style={{ cursor: 'pointer' }}
      />

      {/* Selection halo */}
      {selected && (
        <path
          d={edgePath}
          fill="none"
          stroke="#2563eb"
          strokeWidth={isDone || isActive ? 5 : 4}
          strokeOpacity={0.4}
          strokeLinecap="round"
        />
      )}

      {/* Visible edge */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...style,
          stroke: selected ? '#2563eb' : isDone ? color : isActive ? color : '#94a3b8',
          strokeWidth: selected ? 2.5 : isDone || isActive ? 2.5 : 1.75,
          strokeDasharray: isActive ? '6,6' : 'none',
          transition: 'stroke 0.2s, stroke-width 0.2s',
        }}
      />

      {/* A moving dash overlay keeps in-flight work visible at low zoom. */}
      {isActive && (
        <path
          d={edgePath}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeLinecap="round"
          className="workflow-edge__activity-path"
          aria-hidden="true"
        />
      )}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={18}
        className="edge-selection-path"
        onClick={selectEdge}
        onContextMenu={openContextDelete}
      />

      {/* Curve drag handle — always on the path via getPointAtLength */}
      {isSelectedOrHovered && handlePos && (
        <g
          style={{ pointerEvents: 'all', cursor: 'grab' }}
          onPointerDown={onControlPointerDown}
          onDoubleClick={onControlDoubleClick}
        >
          {/* Transparent hit area */}
          <circle cx={handlePos.x} cy={handlePos.y} r={14} fill="transparent" />
          {/* White ring */}
          <circle
            cx={handlePos.x}
            cy={handlePos.y}
            r={6}
            fill="#ffffff"
            stroke="#2563eb"
            strokeWidth={2.5}
          />
          {/* Blue center dot */}
          <circle
            cx={handlePos.x}
            cy={handlePos.y}
            r={2.5}
            fill="#2563eb"
            style={{ pointerEvents: 'none' }}
          />
        </g>
      )}

      {/* Animated packet when active */}
      {isActive && (
        <circle
          r="5"
          fill={color}
          stroke="#ffffff"
          strokeWidth="1.5"
          className="workflow-edge__packet"
          aria-hidden="true"
        >
          <animateMotion dur="0.9s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}
    </g>
  );
};
