import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {useEffect} from 'react';
import {Link, RouterProvider, createMemoryRouter} from 'react-router';

import {EmbedBlockPage} from '@/features/cms/components/embed/EmbedBlockPage';

/**
 * Unit tests for the public embed widget page served at /_embed/:embedSlug.
 *
 * Contract:
 *   - Fetches /cms/embed/<slug>/ on mount via fetchCMSEmbed()
 *   - Renders the returned block inside a wrapper div using page_css_class
 *   - Injects <base target="_blank"> so internal links pop out of the iframe, and opens
 *     router navigations to other pages in a new tab
 *   - Posts {type: 'i2g-embed-resize', slug, height} to parent on content resize
 *   - Shows "Embed not found." on 404 / fetch error
 */

// Shared mocks
const fetchCMSEmbedMock = vi.fn();

vi.mock('@/features/cms/api', () => ({
  fetchCMSEmbed: (slug: string) => fetchCMSEmbedMock(slug),
}));

vi.mock('@/features/cms/components/rendering/BlockRenderer', () => ({
  BlockRenderer: ({blocks}: {blocks: Array<{block_type: string; data: Record<string, unknown>}>}) => (
    <div data-testid="br">
      {blocks.map((b, i) => (
        <span key={i} data-testid={`blk-${b.block_type}`}>
          {String((b.data as {heading?: string}).heading ?? '')}
        </span>
      ))}
    </div>
  ),
}));

const EmbeddedSchedule = ({scheduleId}: {scheduleId?: string | null}) => (
  <div data-testid="embedded-schedule-route">
    {scheduleId === undefined ? 'no-prop' : scheduleId || 'active-schedule'}
  </div>
);

// Like the project pages: a router link to a page outside the embed.
const EmbeddedProjects = () => <Link to="/projects/abc">Project ABC</Link>;

// Records the body sheet in place when its first effect runs, i.e. the one the widget first paints with.
const sheetsSeenOnMount: Array<string | undefined> = [];
const SheetProbe = () => {
  useEffect(() => {
    sheetsSeenOnMount.push(document.getElementById('itg-embed-body')?.textContent);
  }, []);
  return <p>Sheet probe</p>;
};

const appRoutes = {
  supportsSchedule: (route?: string | null) => route === '/schedule',
  resolve: (route?: string | null) =>
    ({'/schedule': EmbeddedSchedule, '/current-projects': EmbeddedProjects, '/sheet-probe': SheetProbe})[
      route ?? ''
    ] ?? null,
};

// A data router, as in the app: the page blocks navigations that would leave the embed.
const renderAt = (url: string) =>
  render(
    <RouterProvider
      router={createMemoryRouter(
        [{path: '/_embed/:embedSlug', element: <EmbedBlockPage appRoutes={appRoutes} />}],
        {initialEntries: [url]},
      )}
    />,
  );

const renderAtSlug = (slug: string) => renderAt(`/_embed/${slug}`);

// Whether the click behind a navigation may still open a tab (jsdom has no `navigator.userActivation`).
const setUserActivation = (value: {isActive: boolean} | undefined) =>
  Object.defineProperty(window.navigator, 'userActivation', {configurable: true, value});

// jsdom does not implement ResizeObserver; the component uses it to watch
// document height for the iframe-resize postMessage. A no-op stub is enough.
class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

describe('EmbedBlockPage', () => {
  beforeEach(() => {
    fetchCMSEmbedMock.mockReset();
    (globalThis as unknown as {ResizeObserver: typeof ResizeObserver}).ResizeObserver =
      MockResizeObserver as unknown as typeof ResizeObserver;
  });

  afterEach(() => {
    cleanup();
    // Strip any <base> / <style id="itg-embed-*"> tags the component left on <head>
    document
      .querySelectorAll('base, style#itg-embed-body, style#itg-embed-hide-sections')
      .forEach((n) => n.remove());
    setUserActivation(undefined);
    vi.restoreAllMocks();
  });

  it('pads an app-route widget inside its frame: 16px, and the 20px phone gutter at 768px and below', async () => {
    fetchCMSEmbedMock.mockResolvedValue({widget_type: 'app_route', app_route: '/current-projects', blocks: []});
    renderAtSlug('projects-widget');
    await screen.findByRole('link', {name: 'Project ABC'});

    expect(screen.getByRole('link', {name: 'Project ABC'}).closest('.cms-embed-app-route')).not.toBeNull();
    const css = (document.getElementById('itg-embed-body')?.textContent ?? '').replace(/\s+/g, ' ');
    expect(css).toMatch(/^@layer itg\.components \{/);
    expect(css).toContain('.cms-embed-app-route { box-sizing: border-box; padding: 16px; }');
    expect(css).toContain('@media (max-width: 768px) { .cms-embed-app-route { padding: 20px; } }');
  });

  it('has the app-route sheet in place before the widget first paints', async () => {
    sheetsSeenOnMount.length = 0;
    fetchCMSEmbedMock.mockResolvedValue({widget_type: 'app_route', app_route: '/sheet-probe', blocks: []});
    renderAtSlug('probe-widget');
    await screen.findByText('Sheet probe');

    // The probe records in its first passive effect, which can run just after the text appears. Waiting for it
    // keeps the check: a child's passive effect runs before its parent's, so a sheet added by a parent's
    // useEffect would still be missing here; only the layout effect puts it in place first.
    await waitFor(() => expect(sheetsSeenOnMount).toHaveLength(1));
    expect(sheetsSeenOnMount[0]).toContain('.cms-embed-app-route');
  });

  it('opens app-route links to other pages in a new tab, keeping the widget', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    fetchCMSEmbedMock.mockResolvedValue({widget_type: 'app_route', app_route: '/current-projects', blocks: []});
    renderAtSlug('projects-widget');

    fireEvent.click(await screen.findByRole('link', {name: 'Project ABC'}));

    expect(open).toHaveBeenCalledWith(`${window.location.origin}/projects/abc`, '_blank');
    expect(screen.getByRole('link', {name: 'Project ABC'})).toBeInTheDocument();
    expect(document.head.querySelector('base')).not.toBeNull();
  });

  it('offers the page in a live region, brought into focus, when no click can open the tab', async () => {
    setUserActivation({isActive: false});
    vi.spyOn(document, 'hasFocus').mockReturnValue(true);
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    fetchCMSEmbedMock.mockResolvedValue({widget_type: 'app_route', app_route: '/current-projects', blocks: []});
    renderAtSlug('projects-widget');

    // Present while empty, so screen readers announce the link when it fills in.
    const status = await screen.findByRole('status');
    expect(status).toBeEmptyDOMElement();
    fireEvent.click(await screen.findByRole('link', {name: 'Project ABC'}));

    expect(open).not.toHaveBeenCalled();
    const fallback = screen.getByRole('link', {name: 'Open the page in a new tab'});
    expect(status).toContainElement(fallback);
    expect(fallback).toHaveAttribute('href', '/projects/abc');
    expect(fallback).toHaveFocus();

    setUserActivation({isActive: true});
    fireEvent.click(fallback);
    expect(open).toHaveBeenCalledWith(`${window.location.origin}/projects/abc`, '_blank');
    expect(screen.queryByRole('link', {name: 'Open the page in a new tab'})).toBeNull();
  });

  it('does not pull focus into the widget while the user is elsewhere on the page', async () => {
    setUserActivation({isActive: false});
    vi.spyOn(document, 'hasFocus').mockReturnValue(false);
    fetchCMSEmbedMock.mockResolvedValue({widget_type: 'app_route', app_route: '/current-projects', blocks: []});
    renderAtSlug('projects-widget');

    fireEvent.click(await screen.findByRole('link', {name: 'Project ABC'}));

    expect(screen.getByRole('link', {name: 'Open the page in a new tab'})).not.toHaveFocus();
  });
});
