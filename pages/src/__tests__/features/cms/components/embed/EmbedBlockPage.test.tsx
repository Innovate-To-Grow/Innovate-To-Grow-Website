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

  it('renders the fetched block', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {heading: 'Embedded'}}],
      page_css_class: '',
    });

    renderAtSlug('contact-widget');

    await waitFor(() => expect(screen.getByTestId('blk-rich_text')).toHaveTextContent('Embedded'));
    expect(fetchCMSEmbedMock).toHaveBeenCalledWith('contact-widget');
  });

  it('applies page_css_class to the wrapper', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: 'special-wrapper',
    });

    const {container} = renderAtSlug('c');
    await waitFor(() => expect(container.querySelector('.special-wrapper')).toBeInTheDocument());
  });

  it('falls back to cms-page wrapper when page_css_class is empty', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
    });

    const {container} = renderAtSlug('c');
    await waitFor(() => expect(container.querySelector('.cms-page')).toBeInTheDocument());
  });

  it('ignores page_css if an older API still sends it', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      page_css: '.mine { color: red; }',
    });

    const {container} = renderAtSlug('c');
    await waitFor(() => expect(container.querySelector('.cms-page')).toBeInTheDocument());

    expect(document.getElementById('itg-embed-page-css')).toBeNull();
    expect(document.head.textContent).not.toContain('.mine');
  });

  it('injects <base target="_blank"> so links pop out of the iframe', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
    });

    renderAtSlug('c');
    await waitFor(() => {
      const base = document.head.querySelector('base');
      expect(base).not.toBeNull();
      expect(base?.target).toBe('_blank');
    });
  });

  it('shows "Embed not found." when the fetch fails', async () => {
    fetchCMSEmbedMock.mockRejectedValue(new Error('404'));
    renderAtSlug('nope');
    await waitFor(() => expect(screen.getByText(/embed not found/i)).toBeInTheDocument());
  });

  it('does not render anything until data arrives (no flash of broken UI)', () => {
    // Never-resolving promise
    fetchCMSEmbedMock.mockReturnValue(new Promise(() => {}));
    const {container} = renderAtSlug('pending');
    // No block, no error — just empty
    expect(container.querySelector('[data-testid="br"]')).toBeNull();
    expect(screen.queryByText(/embed not found/i)).not.toBeInTheDocument();
  });
});
