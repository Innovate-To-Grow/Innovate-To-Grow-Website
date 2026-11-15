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

  it.each(['true', 'yes', 'on', 'TRUE', 'YES'])(
    'treats ?hide-titles=%s as truthy',
    async (value) => {
      fetchCMSEmbedMock.mockResolvedValue({
        blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
        page_css_class: '',
        hide_section_titles: false,
      });

      renderAt(`/_embed/widget?hide-titles=${value}`);

      await waitFor(() => {
        expect(document.getElementById('itg-embed-hide-sections')).not.toBeNull();
      });
    },
  );

  it.each(['false', 'no', '0', 'off', ''])(
    'treats ?hide-titles=%s as NOT truthy',
    async (value) => {
      fetchCMSEmbedMock.mockResolvedValue({
        blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
        page_css_class: '',
        hide_section_titles: false,
      });

      renderAt(`/_embed/widget?hide-titles=${value}`);

      await waitFor(() => expect(screen.getByTestId('blk-rich_text')).toBeInTheDocument());
      expect(document.getElementById('itg-embed-hide-sections')).toBeNull();
    },
  );

  it('hides titles when the API flag is true even if the query param is false', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      hide_section_titles: true,
    });

    renderAt('/_embed/widget?hide-titles=false');

    await waitFor(() => {
      expect(document.getElementById('itg-embed-hide-sections')).not.toBeNull();
    });
  });

  it('removes #itg-embed-hide-sections on unmount', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      hide_section_titles: true,
    });

    const {unmount} = renderAtSlug('widget');
    await waitFor(() =>
      expect(document.getElementById('itg-embed-hide-sections')).not.toBeNull(),
    );
    unmount();
    expect(document.getElementById('itg-embed-hide-sections')).toBeNull();
  });

  it('does not inject hide-titles stylesheet when both flag and query are off', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      hide_section_titles: false,
    });

    renderAtSlug('widget');
    await waitFor(() => expect(screen.getByTestId('blk-rich_text')).toBeInTheDocument());
    expect(document.getElementById('itg-embed-hide-sections')).toBeNull();
  });
});
