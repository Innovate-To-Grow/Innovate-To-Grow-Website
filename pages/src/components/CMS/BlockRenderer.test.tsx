import {render} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {CMSBlock} from '../../features/cms/api';
import {BlockRenderer} from './BlockRenderer';

/**
 * Sanity tests for the block-type -> component map. These guard against a
 * future developer accidentally dropping `embed` or `embed_widget` from
 * `BLOCK_COMPONENTS` and silently rendering nothing.
 */

describe('BlockRenderer', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders an <iframe> for the "embed" block type', () => {
    const blocks: CMSBlock[] = [
      {
        block_type: 'embed',
        sort_order: 0,
        data: {src: 'https://docs.google.com/forms/d/xyz/viewform'},
      },
    ];
    const {container} = render(<BlockRenderer blocks={blocks} />);
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('src')).toBe(
      'https://docs.google.com/forms/d/xyz/viewform',
    );
  });

  it('renders an <iframe> for the "embed_widget" block type', () => {
    const blocks: CMSBlock[] = [
      {
        block_type: 'embed_widget',
        sort_order: 0,
        data: {slug: 'schedule-embed'},
      },
    ];
    const {container} = render(<BlockRenderer blocks={blocks} />);
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('src')).toBe('/_embed/schedule-embed');
  });

  it('logs a console.warn and renders nothing for an unknown block type', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const blocks: CMSBlock[] = [
      {block_type: 'nonexistent_block', sort_order: 0, data: {}},
    ];
    const {container} = render(<BlockRenderer blocks={blocks} />);
    expect(container.textContent).toBe('');
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Unknown CMS block type'),
    );
  });

  it('renders multiple block types in order', () => {
    const blocks: CMSBlock[] = [
      {
        block_type: 'embed',
        sort_order: 0,
        data: {src: 'https://docs.google.com/a'},
      },
      {
        block_type: 'embed_widget',
        sort_order: 1,
        data: {slug: 'schedule-embed'},
      },
    ];
    const {container} = render(<BlockRenderer blocks={blocks} />);
    const iframes = container.querySelectorAll('iframe');
    expect(iframes).toHaveLength(2);
    expect(iframes[0].getAttribute('src')).toContain('docs.google.com');
    expect(iframes[1].getAttribute('src')).toBe('/_embed/schedule-embed');
  });

  it('filters out falsy blocks defensively', () => {
    const blocks = [
      null,
      undefined,
      {
        block_type: 'embed_widget',
        sort_order: 0,
        data: {slug: 'schedule-embed'},
      },
    ] as unknown as CMSBlock[];
    const {container} = render(<BlockRenderer blocks={blocks} />);
    expect(container.querySelectorAll('iframe')).toHaveLength(1);
  });
});
