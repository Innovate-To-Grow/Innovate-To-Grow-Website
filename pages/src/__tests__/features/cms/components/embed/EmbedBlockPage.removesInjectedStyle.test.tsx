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

  it('removes its injected <style> and <base> tags on unmount', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
    });

    const {unmount} = renderAtSlug('c');
    await waitFor(() => {
      expect(document.getElementById('itg-embed-body')).not.toBeNull();
      expect(document.head.querySelector('base')).not.toBeNull();
    });

    unmount();
    expect(document.getElementById('itg-embed-body')).toBeNull();
    expect(document.head.querySelector('base')).toBeNull();
  });

  it('reports the content height, so the frame shrinks when the content does', async () => {
    const postMessageSpy = vi.fn();
    Object.defineProperty(window, 'parent', {configurable: true, value: {postMessage: postMessageSpy}});
    let onResize: () => void = () => {};
    (globalThis as unknown as {ResizeObserver: unknown}).ResizeObserver = class {
      constructor(callback: () => void) {
        onResize = callback;
      }
      observe() {}
      disconnect() {}
    };
    // In a frame, scrollHeight never drops below the frame's own (last reported) height.
    Object.defineProperty(document.documentElement, 'scrollHeight', {configurable: true, value: 1200});
    let contentHeight = 1200;
    vi.spyOn(document.documentElement, 'getBoundingClientRect').mockImplementation(
      () => ({height: contentHeight}) as DOMRect,
    );
    fetchCMSEmbedMock.mockResolvedValue({blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}]});

    renderAtSlug('widget');
    await waitFor(() => expect(postMessageSpy).toHaveBeenCalledWith(expect.objectContaining({height: 1200}), '*'));

    contentHeight = 400.4;
    onResize();
    expect(postMessageSpy).toHaveBeenLastCalledWith({type: 'i2g-embed-resize', slug: 'widget', height: 401}, '*');

    // Nothing rendered (a lazy page still loading): the frame keeps its height instead of collapsing.
    contentHeight = 0;
    postMessageSpy.mockClear();
    onResize();
    expect(postMessageSpy).not.toHaveBeenCalled();

    Object.defineProperty(window, 'parent', {configurable: true, value: window});
    Reflect.deleteProperty(document.documentElement, 'scrollHeight');
  });

  it('keeps block widgets transparent but gives app-route widgets the page background', async () => {
    fetchCMSEmbedMock.mockResolvedValue({blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}]});
    renderAtSlug('blocks-widget');
    await waitFor(() => expect(screen.getByTestId('blk-rich_text')).toBeInTheDocument());
    expect(document.getElementById('itg-embed-body')?.textContent).toContain('background: transparent !important');
    expect(document.getElementById('itg-embed-body')?.textContent).not.toContain('.cms-embed-app-route');
    cleanup();

    fetchCMSEmbedMock.mockResolvedValue({widget_type: 'app_route', app_route: '/current-projects', blocks: []});
    renderAtSlug('projects-widget');
    await screen.findByRole('link', {name: 'Project ABC'});
    const css = document.getElementById('itg-embed-body')?.textContent;
    expect(css).toContain('background: var(--itg-color-bg-page, #fff) !important');
    expect(css).not.toContain('transparent');
  });
});
