import {act, cleanup, render, renderHook, waitFor} from '@testing-library/react';
import {MemoryRouter, useLocation, useNavigate} from 'react-router';
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
import {navigateRef, navigateTo, ORIGIN, ROUTE_TITLES} from '@/__tests__/hooks/usePageTrackingFixtures';

function NavigateBridge() {
  const navigate = useNavigate();
  useEffect(() => {
    navigateRef.current = navigate;
  });
  return null;
}

function RouteTitle() {
  const {pathname} = useLocation();
  useEffect(() => {
    const title = ROUTE_TITLES[pathname];
    if (title) document.title = title;
  }, [pathname]);
  return null;
}

function Tracker() {
  usePageTracking();
  return null;
}

/** The app's order: the route's title first, then the page, then the shell that tracks it. */
function renderApp(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <NavigateBridge />
      <RouteTitle />
      <Tracker />
    </MemoryRouter>,
  );
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

  describe('Siteimprove', () => {
    let push: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      push = vi.fn();
      (window as {_sz?: unknown})._sz = {push};
      document.title = 'Innovate to Grow | School of Engineering';
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('announces client-side route changes, but not the first page view it counts itself', () => {
      renderApp('/presenting-teams');
      expect(push).not.toHaveBeenCalled();

      navigateTo('/current-projects?class=CSE');

      expect(push).toHaveBeenCalledOnce();
      expect(push).toHaveBeenCalledWith([
        'trackdynamic',
        {url: `${ORIGIN}/current-projects?class=CSE`, title: 'Current Projects | Innovate to Grow'},
      ]);
    });

    it('waits for a page that names itself from its data, so the view does not carry the last page title', async () => {
      renderApp('/current-projects');

      navigateTo('/projects/b158588f');
      expect(push).not.toHaveBeenCalled();

      act(() => {
        document.title = 'Solar drone | Innovate to Grow';
      });

      await waitFor(() => expect(push).toHaveBeenCalledOnce());
      expect(push).toHaveBeenCalledWith([
        'trackdynamic',
        {url: `${ORIGIN}/projects/b158588f`, title: 'Solar drone | Innovate to Grow'},
      ]);
    });

    it('does not wait for a title for ever', () => {
      vi.useFakeTimers({toFake: ['setTimeout', 'clearTimeout']});
      renderApp('/current-projects');

      navigateTo('/projects/b158588f');
      act(() => {
        vi.advanceTimersByTime(5000);
      });

      expect(push).toHaveBeenCalledWith([
        'trackdynamic',
        {url: `${ORIGIN}/projects/b158588f`, title: 'Current Projects | Innovate to Grow'},
      ]);
    });

    it('sends a waiting view with its own address when the visitor moves on first', () => {
      renderApp('/current-projects');
      navigateTo('/projects/b158588f');

      navigateTo('/presenting-teams');

      expect(push.mock.calls.map(([command]) => command)).toEqual([
        ['trackdynamic', {url: `${ORIGIN}/projects/b158588f`, title: 'Current Projects | Innovate to Grow'}],
        ['trackdynamic', {url: `${ORIGIN}/presenting-teams`, title: 'Presenting Teams | Innovate to Grow'}],
      ]);
    });
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
});
