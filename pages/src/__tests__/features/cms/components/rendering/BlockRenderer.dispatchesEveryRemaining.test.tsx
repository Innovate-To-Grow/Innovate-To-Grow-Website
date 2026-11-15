import {cleanup, render} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {CMSBlock} from '@/features/cms/api';
import {BlockRenderer} from '@/features/cms/components/rendering/BlockRenderer';

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
