import {cleanup, render, screen, waitFor} from '@testing-library/react';
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

  it('passes schedule_id to embedded schedule app routes', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      widget_type: 'app_route',
      app_route: '/schedule',
      schedule_id: 'schedule-123',
      blocks: [],
      page_css_class: '',
    });

    renderAtSlug('schedule-widget');

    await waitFor(() =>
      expect(screen.getByTestId('embedded-schedule-route')).toHaveTextContent('schedule-123'),
    );
  });

  it('prefers the block-level ?schedule_id= override over the widget default', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      widget_type: 'app_route',
      app_route: '/schedule',
      schedule_id: 'schedule-123',
      blocks: [],
      page_css_class: '',
    });

    renderAt('/_embed/schedule-widget?schedule_id=6F1D2C3B-4A5E-4F60-8A9B-0C1D2E3F4A5B');

    await waitFor(() =>
      expect(screen.getByTestId('embedded-schedule-route')).toHaveTextContent(
        '6f1d2c3b-4a5e-4f60-8a9b-0c1d2e3f4a5b',
      ),
    );
  });

  it('ignores a malformed ?schedule_id= and falls back to the widget default', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      widget_type: 'app_route',
      app_route: '/schedule',
      schedule_id: 'schedule-123',
      blocks: [],
      page_css_class: '',
    });

    renderAt('/_embed/schedule-widget?schedule_id=../../etc');

    await waitFor(() =>
      expect(screen.getByTestId('embedded-schedule-route')).toHaveTextContent('schedule-123'),
    );
  });

  it('falls back to the active schedule when neither block nor widget pins one', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      widget_type: 'app_route',
      app_route: '/schedule',
      schedule_id: null,
      blocks: [],
      page_css_class: '',
    });

    renderAtSlug('schedule-widget');

    await waitFor(() =>
      expect(screen.getByTestId('embedded-schedule-route')).toHaveTextContent('active-schedule'),
    );
  });
});
