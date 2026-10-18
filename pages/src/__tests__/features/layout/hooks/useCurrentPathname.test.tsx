import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {notifyRouteChange, useCurrentPathname} from '@/features/layout/hooks/useCurrentPathname';

afterEach(() => {
  cleanup();
  window.history.replaceState(null, '', '/');
});

describe('useCurrentPathname', () => {
  it('reads the location and updates on route-change and popstate events', () => {
    window.history.replaceState(null, '', '/news');
    const {result} = renderHook(() => useCurrentPathname());
    expect(result.current).toBe('/news');

    act(() => {
      window.history.pushState(null, '', '/past-projects');
      notifyRouteChange('/past-projects');
    });
    expect(result.current).toBe('/past-projects');

    act(() => {
      window.history.replaceState(null, '', '/about');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(result.current).toBe('/about');
  });
});
