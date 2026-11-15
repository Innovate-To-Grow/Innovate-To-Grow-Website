import {act, cleanup, renderHook} from '@testing-library/react';
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

  it('skips tracking for isolated routes', () => {
    mockIsIsolatedRoute.mockReturnValue(true);

    renderHook(() => usePageTracking(), {wrapper: makeWrapper('/about')});

    expect(mockIsIsolatedRoute).toHaveBeenCalledWith('/about', '');
    expect(mockTrackPageView).not.toHaveBeenCalled();
  });

  it('tracks a plain pathname without its query string', () => {
    renderHook(() => usePageTracking(), {wrapper: makeWrapper('/about?foo=1')});

    expect(mockTrackPageView).toHaveBeenCalledWith({
      path: '/about',
      referrer: document.referrer,
    });
  });

  it('encodes the event query param on the registration route', () => {
    renderHook(() => usePageTracking(), {
      wrapper: makeWrapper('/event-registration?event=Capstone Day'),
    });

    expect(mockTrackPageView).toHaveBeenCalledWith({
      path: '/event-registration?event=Capstone%20Day',
      referrer: document.referrer,
    });
  });

  it('dedupes the same current path across different raw query strings', () => {
    const {result} = renderHook(() => usePageTracking(), {
      wrapper: makeWrapper('/about?foo=1'),
    });
    expect(mockTrackPageView).toHaveBeenCalledTimes(1);

    act(() => {
      navigateRef.current?.('/about?foo=2');
    });

    expect(result.current).toBeUndefined();
    expect(mockTrackPageView).toHaveBeenCalledTimes(1);
  });

  it('credits a client-side page view to the previous in-app page, not to the landing referrer', () => {
    renderHook(() => usePageTracking(), {wrapper: makeWrapper('/presenting-teams?class=CSE')});

    act(() => {
      navigateRef.current?.('/projects/b158588f');
    });
    act(() => {
      navigateRef.current?.('/current-projects');
    });

    expect(mockTrackPageView.mock.calls.map(([view]) => view)).toEqual([
      {path: '/presenting-teams', referrer: document.referrer},
      {path: '/projects/b158588f', referrer: `${window.location.origin}/presenting-teams`},
      {path: '/current-projects', referrer: `${window.location.origin}/projects/b158588f`},
    ]);
  });
});
