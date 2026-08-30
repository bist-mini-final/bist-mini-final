import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EdgeProps } from '@xyflow/react';
import { CustomEdge } from './CustomEdge';

vi.mock('@xyflow/react', () => ({
  BaseEdge: ({ id, path, style }: { id: string; path: string; style: React.CSSProperties }) => (
    <path data-testid={`base-${id}`} d={path} style={style} />
  ),
  getBezierPath: () => ['M 0 0 L 100 0'],
  useReactFlow: () => ({
    setEdges: vi.fn(),
    screenToFlowPosition: vi.fn(),
  }),
}));

const edgeProps = (active: boolean): EdgeProps => ({
  id: 'edge-1',
  source: 'source',
  target: 'target',
  sourceX: 0,
  sourceY: 0,
  targetX: 100,
  targetY: 0,
  sourcePosition: 'right',
  targetPosition: 'left',
  data: { active, done: false, color: '#10b981' },
  selected: false,
  markerEnd: undefined,
  style: {},
} as EdgeProps);

describe('CustomEdge', () => {
  it('renders a moving dash and packet while the target module is running', () => {
    const { container } = render(
      <svg><CustomEdge {...edgeProps(true)} /></svg>,
    );

    expect(container.querySelector('[data-execution-state="active"]')).not.toBeNull();
    expect(container.querySelector('.workflow-edge__activity-path')).not.toBeNull();
    expect(container.querySelector('.workflow-edge__packet animateMotion')).not.toBeNull();
  });

  it('does not render activity indicators for an idle edge', () => {
    const { container } = render(
      <svg><CustomEdge {...edgeProps(false)} /></svg>,
    );

    expect(container.querySelector('[data-execution-state="idle"]')).not.toBeNull();
    expect(container.querySelector('.workflow-edge__activity-path')).toBeNull();
    expect(container.querySelector('.workflow-edge__packet')).toBeNull();
  });
});
