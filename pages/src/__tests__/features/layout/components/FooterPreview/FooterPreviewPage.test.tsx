import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {FooterPreviewPage} from '@/features/layout/components/FooterPreview/FooterPreviewPage';

/**
 * The admin footer editor's preview frame (/_footer-preview): it announces itself to the parent,
 * renders the real Footer from the content a trusted parent posts, and reports its height.
 */

vi.mock('@/components/SafeHtml/SafeHtml', () => ({
  SafeHtml: ({html, className}: {html: string; className?: string}) => (
    <div data-testid="safe-html" className={className}>
      {html}
    </div>
  ),
}));

const PREVIEW_NONCE = 'footer-preview-nonce';

const parentMessage = (data: Record<string, unknown>, init: MessageEventInit = {}) =>
  new MessageEvent('message', {
    origin: window.location.origin,
    source: window.parent,
    ...init,
    data: {type: 'cms-footer-preview', nonce: PREVIEW_NONCE, ...data},
  });

const CONTENT = {
  copyright: '© 2026 Innovate To Grow',
  columns: [{title: 'Programs', links: [{label: 'Capstone', href: '/capstone'}]}],
};

describe('FooterPreviewPage', () => {
  let postMessageSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    window.history.replaceState({}, '', `/_footer-preview?nonce=${PREVIEW_NONCE}`);
    postMessageSpy = vi.fn();
    Object.defineProperty(window, 'parent', {configurable: true, value: {postMessage: postMessageSpy}});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    Object.defineProperty(window, 'parent', {configurable: true, value: window});
    window.history.replaceState({}, '', '/');
  });

  it('waits for content and announces itself to the parent', () => {
    render(<FooterPreviewPage />);

    expect(screen.getByText(/waiting for footer data/i)).toBeInTheDocument();
    expect(postMessageSpy).toHaveBeenCalledWith(
      {type: 'cms-footer-preview-ready', nonce: PREVIEW_NONCE},
      window.location.origin,
    );
  });

  it('renders the real footer from posted content and reports its height', async () => {
    // jsdom lays nothing out, so give the document a height to report.
    Object.defineProperty(document.documentElement, 'scrollHeight', {configurable: true, value: 412});
    render(<FooterPreviewPage />);

    act(() => {
      window.dispatchEvent(parentMessage({content: CONTENT}));
    });

    expect(await screen.findByText('© 2026 Innovate To Grow')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Capstone'})).toHaveAttribute('href', '/capstone');
    expect(document.querySelector('footer.site-footer')).not.toBeNull();
    await waitFor(() =>
      expect(postMessageSpy).toHaveBeenCalledWith(
        {type: 'cms-footer-preview-resize', nonce: PREVIEW_NONCE, height: 412},
        window.location.origin,
      ),
    );
    delete (document.documentElement as unknown as Record<string, unknown>).scrollHeight;
  });

  it('updates when the editor posts again', async () => {
    render(<FooterPreviewPage />);
    act(() => {
      window.dispatchEvent(parentMessage({content: CONTENT}));
    });
    act(() => {
      window.dispatchEvent(parentMessage({content: {...CONTENT, copyright: 'Updated'}}));
    });

    expect(await screen.findByText('Updated')).toBeInTheDocument();
  });

  it.each([
    ['a wrong nonce', parentMessage({content: CONTENT, nonce: 'other'})],
    ['another window', parentMessage({content: CONTENT}, {source: null})],
    ['an untrusted origin', parentMessage({content: CONTENT}, {origin: 'https://evil.example'})],
    ['another message type', parentMessage({type: 'cms-block-preview', content: CONTENT})],
    ['content that is not an object', parentMessage({content: ['not', 'an', 'object']})],
  ])('ignores %s', (_label, event) => {
    render(<FooterPreviewPage />);

    act(() => {
      window.dispatchEvent(event);
    });

    expect(screen.getByText(/waiting for footer data/i)).toBeInTheDocument();
  });
});
