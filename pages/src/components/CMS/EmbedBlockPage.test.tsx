import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter, Route, Routes} from 'react-router-dom';

import {EmbedBlockPage} from './EmbedBlockPage';

/**
 * Unit tests for the public embed widget page served at /_embed/:embedSlug.
 *
 * Contract:
 *   - Fetches /cms/embed/<slug>/ on mount via fetchCMSEmbed()
 *   - Renders the returned block inside a wrapper div using page_css_class
 *   - Injects page_css as <style id="itg-embed-page-css">
 *   - Injects <base target="_blank"> so internal links pop out of the iframe
 *   - Posts {type: 'i2g-embed-resize', slug, height} to parent on content resize
 *   - Shows "Embed not found." on 404 / fetch error
 */

// Shared mocks
const fetchCMSEmbedMock = vi.fn();

vi.mock('../../features/cms/api', () => ({
  fetchCMSEmbed: (slug: string) => fetchCMSEmbedMock(slug),
}));

vi.mock('./BlockRenderer', () => ({
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

const renderAtSlug = (slug: string) =>
  render(
    <MemoryRouter initialEntries={[`/_embed/${slug}`]}>
      <Routes>
        <Route path="/_embed/:embedSlug" element={<EmbedBlockPage />} />
      </Routes>
    </MemoryRouter>,
  );

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
    document.querySelectorAll('base, style#itg-embed-body, style#itg-embed-page-css').forEach((n) => n.remove());
    vi.restoreAllMocks();
  });

  it('renders the fetched block', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {heading: 'Embedded'}}],
      page_css_class: '',
      page_css: '',
    });

    renderAtSlug('contact-widget');

    await waitFor(() => expect(screen.getByTestId('blk-rich_text')).toHaveTextContent('Embedded'));
    expect(fetchCMSEmbedMock).toHaveBeenCalledWith('contact-widget');
  });

  it('applies page_css_class to the wrapper', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: 'special-wrapper',
      page_css: '',
    });

    const {container} = renderAtSlug('c');
    await waitFor(() => expect(container.querySelector('.special-wrapper')).toBeInTheDocument());
  });

  it('falls back to cms-page wrapper when page_css_class is empty', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      page_css: '',
    });

    const {container} = renderAtSlug('c');
    await waitFor(() => expect(container.querySelector('.cms-page')).toBeInTheDocument());
  });

  it('injects page_css into <head> as a scoped style tag', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      page_css: '.mine { color: red; }',
    });

    renderAtSlug('c');
    await waitFor(() => {
      const tag = document.getElementById('itg-embed-page-css');
      expect(tag).not.toBeNull();
      expect(tag?.textContent).toContain('.mine { color: red; }');
    });
  });

  it('injects <base target="_blank"> so links pop out of the iframe', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      page_css: '',
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

  it('posts i2g-embed-resize to window.parent when running inside an iframe', async () => {
    const postMessageSpy = vi.fn();
    Object.defineProperty(window, 'parent', {
      configurable: true,
      value: {postMessage: postMessageSpy},
    });

    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      page_css: '',
    });

    renderAtSlug('widget');

    await waitFor(() => {
      expect(postMessageSpy).toHaveBeenCalledWith(
        expect.objectContaining({type: 'i2g-embed-resize', slug: 'widget'}),
        '*',
      );
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
      page_css: '',
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

  it('removes its injected <style> and <base> tags on unmount', async () => {
    fetchCMSEmbedMock.mockResolvedValue({
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
      page_css_class: '',
      page_css: '.x{}',
    });

    const {unmount} = renderAtSlug('c');
    await waitFor(() => {
      expect(document.getElementById('itg-embed-page-css')).not.toBeNull();
      expect(document.head.querySelector('base')).not.toBeNull();
    });

    unmount();
    expect(document.getElementById('itg-embed-page-css')).toBeNull();
    expect(document.head.querySelector('base')).toBeNull();
  });
});
