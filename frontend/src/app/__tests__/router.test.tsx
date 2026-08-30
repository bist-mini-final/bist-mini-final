import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { navigateTo, useAppLocation } from '../router';

describe('app router location state', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('updates consumers when only the query string changes', () => {
    window.history.replaceState({}, '', '/playground?question=first');
    const { result } = renderHook(() => useAppLocation());

    act(() => navigateTo('/playground?question=second#reader'));

    expect(result.current).toEqual({
      pathname: '/playground',
      search: '?question=second',
      hash: '#reader',
    });
  });
});
