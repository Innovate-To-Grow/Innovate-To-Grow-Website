import {act, cleanup, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {BlockPreviewPage} from './BlockPreviewPage';

/**
 * Unit tests for the admin block-preview iframe page.
 *
 * Contract:
 *   - On mount, posts {type: 'cms-block-preview-ready'} to window.parent
 *   - Listens for {type: 'cms-block-preview', block, pageCssClass} messages
 *   - Renders the single block via BlockRenderer inside a wrapper div with
 *     the provided pageCssClass (or 'cms-page' default)
 *   - Shows a placeholder until the first valid message arrives
 *   - Ignores messages of the wrong shape (silent — no throw)
 */

// Mock the concrete block components via BlockRenderer so we can assert on
// rendered output without pulling in styling/API deps. We spy on
// BlockRenderer's input.
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

describe('BlockPreviewPage', () => {
  let postMessageSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
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
    vi.restoreAllMocks();
    Object.defineProperty(window, 'parent', {
      configurable: true,
      value: window,
    });
  });

  it('renders the waiting-for-data placeholder on mount', () => {
    render(<BlockPreviewPage />);
    expect(screen.getByText(/waiting for block data/i)).toBeInTheDocument();
  });

  it('posts a ready signal to window.parent on mount', () => {
    render(<BlockPreviewPage />);
    expect(postMessageSpy).toHaveBeenCalledWith(
      expect.objectContaining({type: 'cms-block-preview-ready'}),
      '*',
    );
  });

  it('renders the block on receiving a valid cms-block-preview message', () => {
    render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
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

  it('applies pageCssClass when provided', () => {
    const {container} = render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            type: 'cms-block-preview',
            block: {block_type: 'rich_text', sort_order: 0, data: {heading: 'x'}},
            pageCssClass: 'custom-wrapper',
          },
        }),
      );
    });
    expect(container.querySelector('.custom-wrapper')).toBeInTheDocument();
  });

  it('falls back to cms-page class when pageCssClass is empty', () => {
    const {container} = render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            type: 'cms-block-preview',
            block: {block_type: 'rich_text', sort_order: 0, data: {}},
          },
        }),
      );
    });
    expect(container.querySelector('.cms-page')).toBeInTheDocument();
  });

  it('ignores messages with a different type', () => {
    render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'unrelated-message', block: {block_type: 'rich_text', sort_order: 0, data: {}}},
        }),
      );
    });
    expect(screen.getByText(/waiting for block data/i)).toBeInTheDocument();
  });

  it('ignores messages with no payload (e.g. primitive string)', () => {
    render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(new MessageEvent('message', {data: 'plain-string'}));
    });
    expect(screen.getByText(/waiting for block data/i)).toBeInTheDocument();
  });

  it('updates the rendered block when subsequent messages arrive', () => {
    render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            type: 'cms-block-preview',
            block: {block_type: 'rich_text', sort_order: 0, data: {heading: 'First'}},
          },
        }),
      );
    });
    expect(screen.getByTestId('blk-rich_text')).toHaveTextContent('First');

    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            type: 'cms-block-preview',
            block: {block_type: 'rich_text', sort_order: 0, data: {heading: 'Second'}},
          },
        }),
      );
    });
    expect(screen.getByTestId('blk-rich_text')).toHaveTextContent('Second');
  });

  it('removes the message listener on unmount (no leaked handler)', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const {unmount} = render(<BlockPreviewPage />);
    unmount();
    expect(removeSpy).toHaveBeenCalledWith('message', expect.any(Function));
  });

  it('handles block payload with missing sort_order by defaulting to 0', () => {
    render(<BlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            type: 'cms-block-preview',
            // sort_order intentionally omitted
            block: {block_type: 'rich_text', data: {heading: 'H'}},
          },
        }),
      );
    });
    expect(screen.getByTestId('blk-rich_text')).toBeInTheDocument();
  });
});
