import {act, cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {BlockPreviewPage} from '@/features/cms/components/BlockPreviewPage';

/**
 * The admin block editor previews each block by posting it to /_block-preview,
 * which renders it through the real BlockRenderer. BlockPreviewPage.test.tsx
 * mocks BlockRenderer to test the message protocol; this file keeps the real
 * renderer so every block type the admin offers is known to render a preview.
 */

const PREVIEW_NONCE = 'block-types-nonce';

function sendBlock(block: {block_type: string; data: Record<string, unknown>}) {
  act(() => {
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        source: window.parent,
        data: {type: 'cms-block-preview', nonce: PREVIEW_NONCE, block: {...block, sort_order: 0}},
      }),
    );
  });
}

describe('BlockPreviewPage with the real BlockRenderer', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', `/_block-preview?nonce=${PREVIEW_NONCE}`);
    Object.defineProperty(window, 'parent', {configurable: true, value: {postMessage: vi.fn()}});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    Object.defineProperty(window, 'parent', {configurable: true, value: window});
    window.history.replaceState({}, '', '/');
  });

  function renderPreview() {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const view = render(
      <MemoryRouter>
        <BlockPreviewPage />
      </MemoryRouter>,
    );
    return {...view, warnSpy};
  }

  it('previews a hero block', () => {
    const {container, warnSpy} = renderPreview();
    sendBlock({block_type: 'hero', data: {heading: 'Preview hero', subheading: 'Lead text'}});
    expect(screen.getByRole('heading', {name: 'Preview hero', level: 1})).toBeInTheDocument();
    expect(container.querySelector('.cms-page > .cms-hero .itg-lead')).toHaveTextContent('Lead text');
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('previews a cta_group block, including an item still being edited', () => {
    const {warnSpy} = renderPreview();
    sendBlock({
      block_type: 'cta_group',
      data: {items: [{label: 'Apply', href: '/apply', style: 'primary'}, {label: 'Draft', href: '', style: ''}]},
    });
    expect(screen.getByRole('link', {name: 'Apply'})).toHaveClass('itg-btn-primary');
    expect(screen.getByRole('link', {name: 'Draft'})).toHaveAttribute('href', '#');
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('previews a notice block', () => {
    const {warnSpy} = renderPreview();
    sendBlock({block_type: 'notice', data: {heading: 'Note', style: 'success', body_html: '<p>Done</p>'}});
    expect(screen.getByRole('note')).toHaveClass('itg-notice', 'itg-notice-success');
    expect(screen.getByText('Done')).toBeInTheDocument();
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('previews a numbered_list block', () => {
    const {container, warnSpy} = renderPreview();
    sendBlock({block_type: 'numbered_list', data: {heading: 'Steps', preamble_html: '<p>First:</p>', items: ['A', 'B']}});
    expect(screen.getByRole('heading', {name: 'Steps', level: 2})).toBeInTheDocument();
    expect(container.querySelectorAll('.cms-numbered-list ol > li')).toHaveLength(2);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('previews the default data the admin creates for a new block without crashing', () => {
    // getDefaultData() in the admin editor seeds required fields only.
    const {container, warnSpy} = renderPreview();
    sendBlock({block_type: 'hero', data: {}});
    sendBlock({block_type: 'cta_group', data: {items: []}});
    sendBlock({block_type: 'notice', data: {body_html: ''}});
    expect(screen.getByRole('note')).toBeInTheDocument();
    sendBlock({block_type: 'numbered_list', data: {items: []}});
    expect(container.querySelector('.cms-numbered-list')).not.toBeNull();
    expect(warnSpy).not.toHaveBeenCalled();
  });
});
