import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {useMediaQuery} from '@/features/layout/hooks/useMediaQuery';

afterEach(() => {
  cleanup();
});

describe('useMediaQuery', () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it('is false where matchMedia is unavailable', () => {
    // @ts-expect-error simulate an environment without matchMedia
    delete window.matchMedia;
    const {result} = renderHook(() => useMediaQuery('(max-width: 768px)'));
    expect(result.current).toBe(false);
  });

  it('follows the media query list', () => {
    let matches = false;
    const listeners = new Set<() => void>();
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return matches;
      },
      media: query,
      addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
    })) as unknown as typeof window.matchMedia;

    const {result, unmount} = renderHook(() => useMediaQuery('(max-width: 768px)'));
    expect(result.current).toBe(false);

    act(() => {
      matches = true;
      listeners.forEach((listener) => listener());
    });
    expect(result.current).toBe(true);

    unmount();
    expect(listeners.size).toBe(0);
  });
});
