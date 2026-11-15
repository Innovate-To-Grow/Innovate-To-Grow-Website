import {cleanup, renderHook, waitFor} from '@testing-library/react';
import {MemoryRouter, useNavigate} from 'react-router';
import {useEffect} from 'react';
import type {ReactNode} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const {mockTrackPageView, mockIsIsolatedRoute} = vi.hoisted(() => ({
  mockTrackPageView: vi.fn(),
  mockIsIsolatedRoute: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  trackPageView: mockTrackPageView,
}));

vi.mock('@/lib/preview/isolatedRoute', () => ({
  isIsolatedRoute: (...args: unknown[]) => mockIsIsolatedRoute(...args),
}));

import {usePageTracking} from '@/hooks/usePageTracking';
import {navigateRef} from '@/__tests__/hooks/usePageTrackingFixtures';

function NavigateBridge() {
  const navigate = useNavigate();
  useEffect(() => {
    navigateRef.current = navigate;
  });
  return null;
}

function makeWrapper(initialEntry: string) {
  return function RouterWrapper({children}: {children: ReactNode}) {
    return (
      <MemoryRouter initialEntries={[initialEntry]}>
        <NavigateBridge />
        {children}
      </MemoryRouter>
    );
  };
}

describe('usePageTracking', () => {
  beforeEach(() => {
    navigateRef.current = null;
    mockTrackPageView.mockReset();
    mockIsIsolatedRoute.mockReset();
    mockIsIsolatedRoute.mockReturnValue(false);
    window.requestIdleCallback = ((callback: (deadline: IdleDeadline) => void) => {
      callback({didTimeout: false, timeRemaining: () => 50});
      return 1;
    }) as unknown as Window['requestIdleCallback'];
    window.cancelIdleCallback = vi.fn();
  });

  afterEach(() => {
    cleanup();
    delete (window as {requestIdleCallback?: unknown}).requestIdleCallback;
    delete (window as {cancelIdleCallback?: unknown}).cancelIdleCallback;
    delete (window as {_sz?: unknown})._sz;
  });

  it('falls back to setTimeout when requestIdleCallback is unavailable', async () => {
    delete (window as {requestIdleCallback?: unknown}).requestIdleCallback;

    renderHook(() => usePageTracking(), {wrapper: makeWrapper('/about')});

    expect(mockTrackPageView).not.toHaveBeenCalled();

    await waitFor(
      () => {
        expect(mockTrackPageView).toHaveBeenCalledWith({
          path: '/about',
          referrer: document.referrer,
        });
      },
      {timeout: 2000},
    );
  });
});
