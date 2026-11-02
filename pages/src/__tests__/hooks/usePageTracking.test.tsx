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

/** Stands in for RouteDocumentTitle: names the tab from the route, before the tracker's effects run. */
const ROUTE_TITLES: Record<string, string> = {
  '/presenting-teams': 'Presenting Teams | Innovate to Grow',
  '/current-projects': 'Current Projects | Innovate to Grow',
};

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

const navigateTo = (to: string) => {
  act(() => {
    navigateRef.current?.(to);
  });
};

const ORIGIN = window.location.origin;

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
