import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
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

vi.mock('@/lib/isolatedRoute', () => ({
  isIsolatedRoute: (...args: unknown[]) => mockIsIsolatedRoute(...args),
}));

import {usePageTracking} from '@/hooks/usePageTracking';

const navigateRef: {current: ((to: string) => void) | null} = {current: null};

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

  it('cancels the idle callback on unmount', () => {
    const {unmount} = renderHook(() => usePageTracking(), {
      wrapper: makeWrapper('/about'),
    });
    expect(mockTrackPageView).toHaveBeenCalledTimes(1);

    unmount();

    expect(window.cancelIdleCallback).toHaveBeenCalledWith(1);
  });

  it('skips posting when the route becomes isolated before the idle callback fires', () => {
    mockIsIsolatedRoute
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);

    renderHook(() => usePageTracking(), {wrapper: makeWrapper('/about')});

    expect(mockIsIsolatedRoute).toHaveBeenCalledTimes(2);
    expect(mockTrackPageView).not.toHaveBeenCalled();
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
