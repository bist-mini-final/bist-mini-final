import { describe, expect, it } from 'vitest';
import { collectDescendantNodeIds, summarizeDag } from '../graph';

describe('pipeline graph domain', () => {
  it('summarizes parallel DAG batches without counting duplicate edges', () => {
    const nodes = [{ id: 'source' }, { id: 'left' }, { id: 'right' }, { id: 'sink' }];
    const edges = [
      { source: 'source', target: 'left' },
      { source: 'source', target: 'left' },
      { source: 'source', target: 'right' },
      { source: 'left', target: 'sink' },
      { source: 'right', target: 'sink' },
    ];

    expect(summarizeDag(nodes, edges)).toEqual({ batchCount: 3, hasCycle: false });
  });

  it('detects cycles and selects every downstream node', () => {
    const edges = [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'c' },
      { source: 'c', target: 'a' },
    ];

    expect(summarizeDag([{ id: 'a' }, { id: 'b' }, { id: 'c' }], edges))
      .toEqual({ batchCount: 0, hasCycle: true });
    expect(collectDescendantNodeIds('a', edges)).toEqual(new Set(['a', 'b', 'c']));
  });
});
