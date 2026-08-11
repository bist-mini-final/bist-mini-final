import React from 'react';
import { BaseEdge, EdgeProps, getBezierPath } from '@xyflow/react';

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
  const [edgePath] = getBezierPath({
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

      {/* Animated Glowing Packet Dot when Active */}
      {isActive && (
        <circle r="4" fill={color} className="shadow-lg">
          <animateMotion dur="1.2s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}
    </>
  );
};
