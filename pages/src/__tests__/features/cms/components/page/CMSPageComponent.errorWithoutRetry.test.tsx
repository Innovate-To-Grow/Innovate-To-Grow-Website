import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const clearCMSRouteRedirectChain = vi.hoisted(() => vi.fn());
const performCMSRouteRedirect = vi.hoisted(() => vi.fn());
const useCMSPage = vi.hoisted(() => vi.fn());

vi.mock('@/features/cms/components/page/cmsRouteRedirect', () => ({
  clearCMSRouteRedirectChain,
  performCMSRouteRedirect,
}));

vi.mock('@/features/cms/components/page/useCMSPage', () => ({useCMSPage}));

const blockHeading = vi.hoisted(() => ({text: null as string | null}));

vi.mock('@/features/cms/components/rendering/BlockRenderer', () => ({
  BlockRenderer: () => (
    <div data-testid="blocks">{blockHeading.text ? <h1>{blockHeading.text}</h1> : null}</div>
  ),
}));

vi.mock('@/components/NotFoundPage', () => ({
  NotFoundPage: () => <div data-testid="not-found" />,
}));

import {CMSPageComponent} from '@/features/cms/components/page/CMSPageComponent';

function renderPage(entry = '/old') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <CMSPageComponent />
    </MemoryRouter>,
  );
}

describe('CMSPageComponent redirects and errors', () => {
  beforeEach(() => {
    clearCMSRouteRedirectChain.mockReset();
    performCMSRouteRedirect.mockReset();
    useCMSPage.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows an error without a retry button when a redirect throws', async () => {
    performCMSRouteRedirect.mockImplementation(() => {
      throw new Error('boom');
    });
    useCMSPage.mockReturnValue({
      page: null,
      redirectTo: '/new',
      loading: false,
      error: null,
      isLivePreview: false,
    });

    renderPage('/old');

    expect(await screen.findByText('Something went wrong loading this page.')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Try again'})).toBeNull();
  });

  it('adds no style element of its own, even if the API still sends page_css', () => {
    useCMSPage.mockReturnValue({
      page: {
        slug: 'styled',
        route: '/styled',
        title: 'Styled page',
        page_css_class: 'custom-page',
        page_css: 'body { color: red; }',
        meta_description: '',
        blocks: [],
      },
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: false,
    });
    const stylesBefore = document.head.querySelectorAll('style').length;

    const {container} = renderPage('/styled');

    expect(container.querySelector('.custom-page')).toHaveClass('cms-page');
    expect(document.getElementById('itg-page-css')).toBeNull();
    expect(document.head.querySelectorAll('style')).toHaveLength(stylesBefore);
  });

  it('shows the live preview modal with expiry and a title suffix', () => {
    useCMSPage.mockReturnValue({
      page: {
        slug: 'live',
        route: '/live',
        title: 'Draft page',
        page_css_class: '',
        meta_description: '',
        blocks: [],
        expires_at: '2026-08-24T23:00:00Z',
      },
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: true,
    });

    renderPage('/live');

    expect(
      screen.getByText(
        'Previewing This Page With Content Management System with Admin Permission',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Expires at/)).toBeInTheDocument();
    expect(document.title).toContain('Draft page [Live Preview] | Innovate to Grow');
  });

  it('shows the CMS preview badge after dismissing the modal', () => {
    useCMSPage.mockReturnValue({
      page: {
        slug: 'live',
        route: '/live',
        title: 'Draft page',
        page_css_class: '',
        meta_description: '',
        blocks: [],
        expires_at: '2026-08-24T23:00:00Z',
      },
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: true,
    });

    renderPage('/live');

    fireEvent.click(screen.getByRole('button', {name: 'OK'}));

    expect(screen.getByText('CMS Preview')).toBeInTheDocument();
    expect(screen.getByText(/Expires/)).toBeInTheDocument();
    // The badge is a real button so keyboard users can reopen the notice.
    expect(screen.getByRole('button', {name: /CMS Preview/})).toHaveClass('cms-live-preview-badge');
  });

  it('dismisses the modal when the overlay backdrop is clicked', () => {
    useCMSPage.mockReturnValue({
      page: {
        slug: 'live',
        route: '/live',
        title: 'Draft page',
        page_css_class: '',
        meta_description: '',
        blocks: [],
      },
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: true,
    });

    const {container} = renderPage('/live');

    fireEvent.click(container.querySelector('.cms-live-preview-overlay')!);

    expect(screen.getByText('CMS Preview')).toBeInTheDocument();
  });
});
