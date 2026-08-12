import React, { useCallback } from 'react';
import { BaseEdge, EdgeProps, EdgeLabelRenderer, getBezierPath, useReactFlow } from '@xyflow/react';

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
}) => {
  const { setEdges } = useReactFlow();
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const isActive = data?.active;
  const isDone = data?.done;
  const color = (data?.color as string) || '#6366f1';

  const onDelete = useCallback(
    (event: React.MouseEvent) => {
      event.stopPropagation();
      setEdges((edges) => edges.filter((edge) => edge.id !== id));
    },
    [id, setEdges]
  );

  return (
    <>
      {/* Background / Base Edge */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...style,
          stroke: isDone ? color : isActive ? color : '#cbd5e1',
          strokeWidth: isDone || isActive ? 2.5 : 1.5,
          strokeDasharray: isActive ? '6,6' : 'none',
          transition: 'stroke 0.3s, stroke-width 0.3s',
        }}
      />

      {/* Delete button shown on hover */}
      <EdgeLabelRenderer>
        <div
          className="edge-delete-btn-wrapper"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
        >
          <button
            className="edge-delete-btn"
            onClick={onDelete}
            aria-label="연결 삭제"
            title="연결 삭제"
          >
            ×
          </button>
        </div>
      </EdgeLabelRenderer>

      {/* Animated Glowing Packet Dot when Active */}
      {isActive && (
        <circle r="4" fill={color} className="shadow-lg">
          <animateMotion dur="1.2s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}
    </>
  );
};
