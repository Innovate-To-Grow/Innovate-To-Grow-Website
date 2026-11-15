import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

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
vi.mock('@/features/cms/components/BlockRenderer', () => ({
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

function stubLayoutDimension(
  element: Element,
  property: 'scrollHeight' | 'offsetHeight',
  value: number,
): () => void {
  const original = Object.getOwnPropertyDescriptor(element, property);
  Object.defineProperty(element, property, {configurable: true, value});
  return () => {
    if (original) {
      Object.defineProperty(element, property, original);
    } else {
      delete (element as unknown as Record<string, unknown>)[property];
    }
  };
}

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

  it('accepts messages from the backend origin configured by VITE_API_BASE_URL', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.com/api');
    vi.resetModules();
    const {BlockPreviewPage: ReloadedBlockPreviewPage} = await import('@/features/cms/components/BlockPreviewPage');

    render(<ReloadedBlockPreviewPage />);
    act(() => {
      window.dispatchEvent(
        parentMessage({
          origin: 'https://api.example.com',
          data: {
            type: 'cms-block-preview',
            block: {block_type: 'rich_text', sort_order: 0, data: {heading: 'api-origin'}},
          },
        }),
      );
    });

    expect(screen.getByTestId('blk-rich_text')).toHaveTextContent('api-origin');
    vi.unstubAllEnvs();
  });

  it('targets resize messages to the trusted parent origin from the accepted message', async () => {
    vi.stubEnv('VITE_ADMIN_ORIGIN', 'https://admin.example.com');
    vi.resetModules();
    const {BlockPreviewPage: ReloadedBlockPreviewPage} = await import('@/features/cms/components/BlockPreviewPage');
    const restoreDimensions = [
      stubLayoutDimension(document.documentElement, 'scrollHeight', 240),
      stubLayoutDimension(document.documentElement, 'offsetHeight', 240),
      stubLayoutDimension(document.body, 'scrollHeight', 240),
      stubLayoutDimension(document.body, 'offsetHeight', 240),
    ];

    try {
      render(<ReloadedBlockPreviewPage />);
      act(() => {
        window.dispatchEvent(
          parentMessage({
            origin: 'https://admin.example.com',
            data: {
              type: 'cms-block-preview',
              block: {block_type: 'rich_text', sort_order: 0, data: {heading: 'admin-sent'}},
            },
          }),
        );
      });

      await waitFor(() => {
        expect(postMessageSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'cms-block-preview-resize',
            nonce: PREVIEW_NONCE,
            height: 240,
          }),
          'https://admin.example.com',
        );
      });
    } finally {
      restoreDimensions.forEach((restore) => restore());
      vi.unstubAllEnvs();
    }
  });
});
