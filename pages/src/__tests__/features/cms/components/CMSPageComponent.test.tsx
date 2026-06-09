import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {CMSPageComponent} from '@/features/cms/components/CMSPageComponent';
import type {CMSPageResponse} from '@/features/cms/api';

const cmsComponentMocks = vi.hoisted(() => ({
  hookValue: {
    page: null as CMSPageResponse | null,
    loading: false,
    error: null as string | null,
    isLivePreview: false,
  },
}));

vi.mock('@/features/cms/components/useCMSPage', () => ({
  useCMSPage: vi.fn(() => cmsComponentMocks.hookValue),
}));

vi.mock('@/features/cms/components/BlockRenderer', () => ({
  BlockRenderer: ({blocks}: {blocks: unknown[]}) => (
    <div data-testid="block-renderer">blocks:{blocks.length}</div>
  ),
}));

vi.mock('@/routes/NotFoundPage', () => ({
  NotFoundPage: () => <div>Not found route</div>,
}));

const page = (overrides: Partial<CMSPageResponse> = {}): CMSPageResponse => ({
  slug: 'about',
  route: '/about',
  title: 'About I2G',
  page_css_class: 'cms-about',
  page_css: '.cms-about { color: blue; }',
  meta_description: '',
  blocks: [{block_type: 'rich_text', sort_order: 0, data: {}}],
  ...overrides,
});

const renderCMSPage = (route = '/about') =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <CMSPageComponent />
    </MemoryRouter>,
  );

describe('CMSPageComponent', () => {
  beforeEach(() => {
    document.title = 'Original title';
    document.getElementById('itg-page-css')?.remove();
    cmsComponentMocks.hookValue = {
      page: null,
      loading: false,
      error: null,
      isLivePreview: false,
    };
  });

  it('renders loading, not found, and generic error states', () => {
    cmsComponentMocks.hookValue = {
      page: null,
      loading: true,
      error: null,
      isLivePreview: false,
    };
    const loading = renderCMSPage();
    expect(loading.container.querySelector('.cms-page-loading')).not.toBeNull();
    loading.unmount();

    cmsComponentMocks.hookValue = {
      page: null,
      loading: false,
      error: 'not_found',
      isLivePreview: false,
    };
    const missing = renderCMSPage();
    expect(screen.getByText('Not found route')).toBeInTheDocument();
    missing.unmount();

    cmsComponentMocks.hookValue = {
      page: page(),
      loading: false,
      error: 'error',
      isLivePreview: false,
    };
    renderCMSPage();
    expect(screen.getByText('Something went wrong loading this page.')).toBeInTheDocument();
  });

  it('renders page blocks, updates the document title, and injects page CSS', () => {
    cmsComponentMocks.hookValue = {
      page: page(),
      loading: false,
      error: null,
      isLivePreview: false,
    };

    renderCMSPage();

    expect(screen.getByTestId('block-renderer')).toHaveTextContent('blocks:1');
    expect(document.title).toBe('About I2G | Innovate to Grow');
    expect(document.getElementById('itg-page-css')).toHaveTextContent('.cms-about');
  });

  it('shows and reopens the live preview modal with expiry metadata', () => {
    cmsComponentMocks.hookValue = {
      page: page({expires_at: '2026-06-08T18:45:30Z'}),
      loading: false,
      error: null,
      isLivePreview: true,
    };

    renderCMSPage('/about?cms_live_preview=42');

    expect(document.title).toBe('About I2G [Live Preview] | Innovate to Grow');
    expect(screen.getByText(/Previewing This Page/)).toBeInTheDocument();
    expect(screen.getByText(/Expires at/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'OK'}));
    expect(screen.getByText('CMS Preview')).toBeInTheDocument();

    fireEvent.click(screen.getByText('CMS Preview'));
    expect(screen.getByText(/Previewing This Page/)).toBeInTheDocument();
  });
});
