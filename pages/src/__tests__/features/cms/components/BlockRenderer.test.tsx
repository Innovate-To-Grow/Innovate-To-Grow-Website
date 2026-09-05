import {cleanup, render} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {CMSBlock} from '@/features/cms/api';
import {BlockRenderer} from '@/features/cms/components/BlockRenderer';

/**
 * Sanity tests for the block-type -> component map. These guard against a
 * future developer accidentally dropping `embed` or `embed_widget` from
 * `BLOCK_COMPONENTS` and silently rendering nothing.
 */

describe('BlockRenderer', () => {
  afterEach(() => {
    cleanup();
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

  it('passes previewMode through to embed blocks', () => {
    const blocks: CMSBlock[] = [
      {
        block_type: 'embed',
        sort_order: 0,
        data: {src: 'https://docs.google.com/forms/d/xyz/viewform'},
      },
    ];
    const {container} = render(<BlockRenderer blocks={blocks} previewMode />);
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('loading')).toBe('eager');
  });

  it('passes previewMode through to embed widget blocks', () => {
    const blocks: CMSBlock[] = [
      {
        block_type: 'embed_widget',
        sort_order: 0,
        data: {slug: 'schedule-embed'},
      },
    ];
    const {container} = render(<BlockRenderer blocks={blocks} previewMode />);
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('loading')).toBe('eager');
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

  it('prioritizes only the first homepage image block', () => {
    const blocks: CMSBlock[] = [
      {block_type: 'image_text', sort_order: 0, data: {image_url: '/assets/images/home_img.jpg', body_html: ''}},
      {block_type: 'image_text', sort_order: 1, data: {image_url: '/other.jpg', body_html: ''}},
    ];
    const {container} = render(<BlockRenderer blocks={blocks} prioritizeFirstImage />);
    const images = container.querySelectorAll('img');
    expect(images[0]).toHaveAttribute('loading', 'eager');
    expect(images[0]).toHaveAttribute('fetchpriority', 'high');
    expect(images[0]).toHaveAttribute('decoding', 'async');
    expect(images[0]).toHaveAttribute('width', '1600');
    expect(images[0]).toHaveAttribute('height', '500');
    expect(images[0]).toHaveAttribute('srcset');
    expect(images[1]).toHaveAttribute('loading', 'lazy');
    expect(images[1]).toHaveAttribute('decoding', 'async');
    expect(images[1]).not.toHaveAttribute('fetchpriority');
  });

  it('dispatches every remaining known block type to its component', () => {
    const blocks: CMSBlock[] = [
      {block_type: 'rich_text', sort_order: 0, data: {body_html: '<p>Rich</p>'}},
      {block_type: 'contact_info', sort_order: 1, data: {items: []}},
      {block_type: 'navigation_grid', sort_order: 2, data: {items: []}},
      {block_type: 'link_list', sort_order: 3, data: {items: []}},
      {block_type: 'faq_list', sort_order: 4, data: {items: []}},
      {block_type: 'section_group', sort_order: 5, data: {sections: []}},
      {block_type: 'proposal_cards', sort_order: 6, data: {proposals: []}},
      {block_type: 'table', sort_order: 7, data: {columns: [], rows: []}},
      {
        block_type: 'sponsor_year',
        sort_order: 8,
        data: {year: '2025', sponsors: [{name: 'Acme'}]},
      },
    ];

    const {container} = render(<BlockRenderer blocks={blocks} />);

    expect(container.querySelector('.cms-rich-text')).not.toBeNull();
    expect(container.querySelector('.cms-contact-info')).not.toBeNull();
    expect(container.querySelector('.cms-navigation-grid')).not.toBeNull();
    expect(container.querySelector('.cms-link-list')).not.toBeNull();
    expect(container.querySelector('.cms-faq-list')).not.toBeNull();
    expect(container.querySelector('.cms-section-group')).not.toBeNull();
    expect(container.querySelector('.cms-proposal-cards')).not.toBeNull();
    expect(container.querySelector('.cms-table-block')).not.toBeNull();
    expect(container.querySelector('.cms-sponsor-year')).not.toBeNull();
  });
});
