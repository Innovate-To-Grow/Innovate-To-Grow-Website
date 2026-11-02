import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {lazy, Suspense, type ComponentType} from 'react';
import {createMemoryRouter, Link, Outlet, RouterProvider, type DataRouter} from 'react-router';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {resetPageReloadState} from '@/app/pageReload/pageReload';
import {NavigationPending} from '@/app/router/NavigationPending';

const originalLocation = window.location;

/** A route page whose chunk arrives only when the test says so. */
function deferredPage() {
  let resolve: (module: {default: ComponentType}) => void = () => {};
  const Page = lazy(() => new Promise<{default: ComponentType}>((done) => {
    resolve = done;
  }));
  return {Page, arrive: () => resolve({default: () => <h1>Project detail</h1>})};
}

function buildRouter(Detail: ComponentType, delays: {showDelayMs: number; slowAfterMs: number}) {
  const router: DataRouter = createMemoryRouter(
    [
      {
        path: '/',
        element: (
          <>
            <NavigationPending
              source={{
                subscribe: (listener) => router.subscribe(listener),
                getLocationKey: () => router.state.location.key,
              }}
              {...delays}
            />
            <Outlet />
          </>
        ),
        // As in the app (lazyRoute), every page sits in its own Suspense boundary, which React keeps
        // showing (instead of the fallback) while the next page's chunk loads.
        children: [
          {path: 'list', element: <Suspense fallback={<p>Route spinner</p>}><Link to="/detail">Open project</Link></Suspense>},
          {path: 'detail', element: <Suspense fallback={<p>Route spinner</p>}><Detail /></Suspense>},
        ],
      },
    ],
    {initialEntries: ['/list']},
  );
  return router;
}

describe('NavigationPending', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    resetPageReloadState();
    Object.defineProperty(window, 'location', {configurable: true, value: originalLocation});
  });

  it('shows progress while the next page is still loading, and clears it when the page arrives', async () => {
    const {Page, arrive} = deferredPage();
    const router = buildRouter(Page, {showDelayMs: 20, slowAfterMs: 60_000});
    render(<RouterProvider router={router} />);
    expect(document.querySelector('.itg-navigation-progress')).toBeNull();

    fireEvent.click(screen.getByRole('link', {name: 'Open project'}));

    // The old page stays on screen (the navigation waits in a transition) but no longer looks idle.
    await waitFor(() => expect(document.querySelector('.itg-navigation-progress')).not.toBeNull());
    expect(screen.getByRole('link', {name: 'Open project'})).toBeInTheDocument();
    expect(screen.queryByText('Route spinner')).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('Loading page…');

    await act(async () => arrive());

    expect(await screen.findByRole('heading', {name: 'Project detail'})).toBeInTheDocument();
    expect(document.querySelector('.itg-navigation-progress')).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('');
  });

  it('offers a reload when the page never arrives', async () => {
    const reload = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {href: 'http://localhost/detail', reload},
    });
    const {Page} = deferredPage();
    const router = buildRouter(Page, {showDelayMs: 10, slowAfterMs: 40});
    render(<RouterProvider router={router} />);

    fireEvent.click(screen.getByRole('link', {name: 'Open project'}));

    const notice = await screen.findByRole('alert');
    expect(notice).toHaveTextContent('This page is taking longer than usual to load.');
    fireEvent.click(screen.getByRole('button', {name: 'Reload page'}));
    expect(reload).toHaveBeenCalledOnce();
  });

  it('stays out of the way of a page that is already loaded', async () => {
    const router = buildRouter(() => <h1>Project detail</h1>, {showDelayMs: 0, slowAfterMs: 60_000});
    render(<RouterProvider router={router} />);

    fireEvent.click(screen.getByRole('link', {name: 'Open project'}));

    expect(await screen.findByRole('heading', {name: 'Project detail'})).toBeInTheDocument();
    await new Promise((done) => setTimeout(done, 20));
    expect(document.querySelector('.itg-navigation-progress')).toBeNull();
  });
});
