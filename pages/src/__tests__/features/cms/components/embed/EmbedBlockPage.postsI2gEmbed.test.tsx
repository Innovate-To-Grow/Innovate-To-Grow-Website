import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
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

  it('posts i2g-embed-resize to window.parent when running inside an iframe', async () => {
    const postMessageSpy = vi.fn();
    Object.defineProperty(window, 'parent', {
      configurable: true,
      value: {postMessage: postMessageSpy},
    });
    // jsdom lays nothing out; the rendered widget measures 640px.
    vi.spyOn(document.documentElement, 'getBoundingClientRect').mockReturnValue({height: 640} as DOMRect);

    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
    });

    renderAtSlug('widget');

    await waitFor(() => {
      expect(postMessageSpy).toHaveBeenCalledWith({type: 'i2g-embed-resize', slug: 'widget', height: 640}, '*');
    });

    // Restore
    Object.defineProperty(window, 'parent', {configurable: true, value: window});
  });

  it('does not attempt to postMessage when not inside an iframe (parent === self)', async () => {
    // Ensure window.parent is window (default jsdom)
    Object.defineProperty(window, 'parent', {configurable: true, value: window});
    const postMessageSpy = vi.spyOn(window, 'postMessage');

    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
    });

    renderAtSlug('widget');
    await waitFor(() => expect(screen.getByTestId('blk-rich_text')).toBeInTheDocument());

    // Give effect a tick
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    // No i2g-embed-resize message should have been sent
    const resizeCalls = postMessageSpy.mock.calls.filter(
      (args) => typeof args[0] === 'object' && args[0] && 'type' in (args[0] as object) && (args[0] as {type: string}).type === 'i2g-embed-resize',
    );
    expect(resizeCalls).toEqual([]);
  });

  it('injects a hide-titles stylesheet when hide_section_titles is true in the response', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      hide_section_titles: true,
    });

    renderAtSlug('widget');
    await waitFor(() => {
      const tag = document.getElementById('itg-embed-hide-sections');
      expect(tag).not.toBeNull();
      expect(tag?.textContent).toContain('.section-title');
      expect(tag?.textContent).toContain('display: none');
    });
  });
});
