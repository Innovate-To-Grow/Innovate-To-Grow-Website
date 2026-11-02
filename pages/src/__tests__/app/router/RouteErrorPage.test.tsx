import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {lazy, Suspense} from 'react';
import {createMemoryRouter, Link, Outlet, RouterProvider} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {resetPageReloadState} from '@/app/pageReload/pageReload';
import {RouteErrorPage} from '@/app/router/RouteErrorPage';

const originalLocation = window.location;
const CHUNK_ERROR = 'Failed to fetch dynamically imported module: https://i2g.ucmerced.edu/assets/ProjectDetailPage-CeeAsMfZ.js';
const RUNNING_ENTRY = '/assets/index-OldBuild1.js';
const NEW_ENTRY = '/assets/index-NewBuild2.js';

/** What a reload of the page would get: index.html naming `entry` as the build's script. */
const pageOf = (entry: string) =>
  new Response(`<html><head><script type="module" crossorigin src="${entry}"></script></head></html>`);
const serveBuild = (entry: string) => vi.stubGlobal('fetch', vi.fn(async () => pageOf(entry)));

function Crashes(): never {
  throw new TypeError("Cannot read properties of undefined (reading 'replace')");
}

const MissingChunk = lazy(() => Promise.reject(new TypeError(CHUNK_ERROR)));

const buildRouter = (initialPath: string) =>
  createMemoryRouter(
    [
      {
        path: '/',
        element: (
          <>
            <header>Site menu</header>
            <Outlet />
          </>
        ),
        children: [
          {
            errorElement: <RouteErrorPage />,
            children: [
              {path: 'list', element: <Link to="/crash">Open</Link>},
              {path: 'crash', element: <Crashes />},
              {
                path: 'chunk',
                element: (
                  <Suspense fallback={<p>Loading</p>}>
                    <MissingChunk />
                  </Suspense>
                ),
              },
            ],
          },
        ],
      },
    ],
    {initialEntries: [initialPath]},
  );

function stubLocation() {
  const reload = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {href: 'http://localhost/chunk', origin: 'http://localhost', pathname: '/chunk', reload},
  });
  return reload;
}

describe('RouteErrorPage', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    window.sessionStorage.clear();
    document.head.innerHTML = `<script type="module" crossorigin src="${RUNNING_ENTRY}"></script>`;
    document.title = 'Current Projects | Innovate to Grow';
    serveBuild(NEW_ENTRY);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    resetPageReloadState();
    window.sessionStorage.clear();
    Object.defineProperty(window, 'location', {configurable: true, value: originalLocation});
  });

  it('shows the site error message inside the layout instead of the developer screen', async () => {
    const router = buildRouter('/list');
    render(<RouterProvider router={router} />);

    await act(() => router.navigate('/crash'));

    expect(screen.getByText('Site menu')).toBeInTheDocument();
    const heading = screen.getByRole('heading', {level: 1, name: 'Something went wrong'});
    // Focus announces the heading with its message; an alert as well would read it all twice.
    expect(heading).toHaveFocus();
    expect(heading).toHaveAccessibleDescription(/Reload the page to try again\./);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText('Unexpected Application Error!')).toBeNull();
    expect(document.querySelector('pre')).toBeNull();
    expect(document.body).not.toHaveTextContent("reading 'replace'");
    expect(screen.getByRole('link', {name: 'Go to the home page'})).toHaveAttribute('href', '/');
    expect(document.title).toBe('Something went wrong | Innovate to Grow');
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex');
  });

  it('reloads the page from its Reload page button', async () => {
    const reload = stubLocation();
    const router = buildRouter('/crash');
    render(<RouterProvider router={router} />);

    fireEvent.click(await screen.findByRole('button', {name: 'Reload page'}));

    expect(reload).toHaveBeenCalledOnce();
  });

  it('reloads onto the new build when a route chunk is missing after a deploy, and says so meanwhile', async () => {
    const reload = stubLocation();
    const router = buildRouter('/chunk');
    render(<RouterProvider router={router} />);

    expect(await screen.findByRole('status')).toHaveTextContent('Loading the latest version of the site…');
    expect(fetch).toHaveBeenCalledWith('/chunk', expect.objectContaining({cache: 'no-store'}));
    expect(reload).toHaveBeenCalledOnce();
    expect(screen.queryByRole('heading', {name: 'Something went wrong'})).toBeNull();
    expect(document.title).toBe('Current Projects | Innovate to Grow');
  });

  it('shows the message without reloading while the same build is deployed', async () => {
    // A chunk that fails anyway, or Safari cancelling the page's loads as the visitor goes to another page:
    // a reload would not bring the chunk back, and would cancel that navigation.
    let answer: (response: Response) => void = () => {};
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => (answer = resolve))));
    const reload = stubLocation();
    const router = buildRouter('/chunk');
    render(<RouterProvider router={router} />);

    const checking = await screen.findByRole('status');
    expect(checking).toHaveTextContent('Loading page…');
    // The shared loading indicator: its spinner is decoration only.
    expect(checking.querySelector('.loading-indicator .loading-indicator-spinner')).toHaveAttribute('aria-hidden', 'true');
    act(() => answer(pageOf(RUNNING_ENTRY)));

    expect(await screen.findByRole('heading', {level: 1, name: 'Something went wrong'})).toHaveAccessibleDescription(
      /most likely because the site was just updated/,
    );
    expect(fetch).toHaveBeenCalledOnce();
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Reload page'})).toBeInTheDocument();
  });

  it('never shows the error message before the reload starts', async () => {
    stubLocation();
    const shown: string[] = [];
    // Nodes keep their text after React removes them, so a message that was rendered and replaced still counts.
    const observer = new MutationObserver((records) => {
      records.forEach((record) =>
        record.addedNodes.forEach((node) => {
          if (node.textContent?.includes('Something went wrong')) shown.push(node.textContent);
        }),
      );
    });
    observer.observe(document.body, {childList: true, subtree: true, characterData: true});
    const router = buildRouter('/chunk');
    render(<RouterProvider router={router} />);

    await screen.findByText('Loading the latest version of the site…');
    observer.disconnect();

    expect(shown).toEqual([]);
  });

  it('shows the message, not an endless loader, when session storage refuses the reload stamp', async () => {
    const reload = stubLocation();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    const router = buildRouter('/chunk');
    render(<RouterProvider router={router} />);

    expect(await screen.findByRole('heading', {level: 1, name: 'Something went wrong'})).toHaveAccessibleDescription(
      /most likely because the site was just updated/,
    );
    expect(reload).not.toHaveBeenCalled();
    expect(screen.queryByText(/Loading the latest version/)).toBeNull();
  });

  it('asks for a reload instead of looping when the chunk is still missing after one', async () => {
    const reload = stubLocation();
    window.sessionStorage.setItem('i2g:reloaded-for-new-build-at', String(Date.now()));
    const router = buildRouter('/chunk');
    render(<RouterProvider router={router} />);

    expect(await screen.findByRole('heading', {level: 1, name: 'Something went wrong'})).toHaveAccessibleDescription(
      /most likely because the site was just updated/,
    );
    expect(reload).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Reload page'})).toBeInTheDocument();
  });
});
