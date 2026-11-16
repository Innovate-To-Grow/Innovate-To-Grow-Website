import {act, cleanup, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {BlockPreviewPage} from '@/features/cms/components/preview/BlockPreviewPage';

/**
 * Unit tests for the admin block-preview iframe page.
 *
 * Contract:
 *   - Reads the per-iframe nonce from `?nonce=...`
 *   - On mount, posts {type: 'cms-block-preview-ready', nonce} to window.parent
 *   - Listens for {type: 'cms-block-preview', nonce, block, pageCssClass} messages
 *   - Renders the single block via BlockRenderer inside a wrapper div with
 *     the provided pageCssClass (or 'cms-page' default)
 *   - Shows a placeholder until the first valid message arrives
 *   - Ignores messages of the wrong shape (silent — no throw)
 */

// Mock the concrete block components via BlockRenderer so we can assert on
// rendered output without pulling in styling/API deps. We spy on
// BlockRenderer's input.
vi.mock('@/features/cms/components/rendering/BlockRenderer', () => ({
  BlockRenderer: ({
    blocks,
    previewMode,
  }: {
    blocks: Array<{block_type: string; data: Record<string, unknown>}>;
    previewMode?: boolean;
  }) => (
    <div data-testid="br" data-preview-mode={previewMode ? 'true' : 'false'}>
      {blocks.map((b, i) => (
        <span key={i} data-testid={`blk-${b.block_type}`}>
          {String((b.data as {heading?: string}).heading ?? '')}
        </span>
      ))}
    </div>
  ),
}));

const PREVIEW_NONCE = 'test-preview-nonce';

const parentMessage = (init: MessageEventInit) => {
  const data =
    init.data && typeof init.data === 'object'
      ? {
          ...init.data,
          nonce:
            (init.data as {nonce?: unknown}).nonce ?? PREVIEW_NONCE,
        }
      : init.data;
  return new MessageEvent('message', {
    ...init,
    data,
    source: window.parent,
  });
};

describe('BlockPreviewPage', () => {
  let postMessageSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    window.history.replaceState(
      {},
      '',
      `/_block-preview?nonce=${PREVIEW_NONCE}`,
    );
    // Stub window.parent.postMessage. In jsdom, window.parent === window by default.
    postMessageSpy = vi.fn();
    Object.defineProperty(window, 'parent', {
      configurable: true,
      value: {postMessage: postMessageSpy},
    });
  });

  afterEach(() => {
    // Explicit cleanup — React Testing Library doesn't auto-cleanup reliably
    // in this vitest setup, and leftover components leave message listeners
    // on the shared `window`, causing cross-test interference.
    cleanup();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    Object.defineProperty(window, 'parent', {
      configurable: true,
      value: window,
    });
    window.history.replaceState({}, '', '/');
  });

  it('renders the waiting-for-data placeholder on mount', () => {
    render(<BlockPreviewPage />);
    expect(screen.getByText(/waiting for block data/i)).toBeInTheDocument();
  });

  it('posts a ready signal to window.parent on mount', () => {
    render(<BlockPreviewPage />);
    expect(postMessageSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'cms-block-preview-ready',
        nonce: PREVIEW_NONCE,
      }),
      window.location.origin,
    );
  });

  it('renders the block on receiving a valid cms-block-preview message', () => {
    render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        parentMessage({
          origin: window.location.origin,
          data: {
            type: 'cms-block-preview',
            block: {block_type: 'rich_text', sort_order: 0, data: {heading: 'Hello'}},
          },
        }),
      );
    });
    expect(screen.getByTestId('blk-rich_text')).toHaveTextContent('Hello');
    expect(screen.queryByText(/waiting for block data/i)).not.toBeInTheDocument();
  });

  it('renders blocks in preview mode', () => {
    render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        parentMessage({
          origin: window.location.origin,
          data: {
            type: 'cms-block-preview',
            block: {block_type: 'embed_widget', sort_order: 0, data: {slug: 'schedule-embed'}},
          },
        }),
      );
    });
    expect(screen.getByTestId('br')).toHaveAttribute('data-preview-mode', 'true');
  });

  it('applies pageCssClass when provided', () => {
    const {container} = render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        parentMessage({
          origin: window.location.origin,
          data: {
            type: 'cms-block-preview',
            block: {block_type: 'rich_text', sort_order: 0, data: {heading: 'x'}},
            pageCssClass: 'custom-wrapper',
          },
        }),
      );
    });
    expect(container.querySelector('.custom-wrapper')).toBeInTheDocument();
    expect(container.querySelector('.custom-wrapper')).toHaveClass('cms-page');
  });
});
