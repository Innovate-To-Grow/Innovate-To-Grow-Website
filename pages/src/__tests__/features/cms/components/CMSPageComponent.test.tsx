import {cleanup, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const clearCMSRouteRedirectChain = vi.hoisted(() => vi.fn());
const performCMSRouteRedirect = vi.hoisted(() => vi.fn());
const useCMSPage = vi.hoisted(() => vi.fn());

vi.mock('@/features/cms/components/cmsRouteRedirect', () => ({
  clearCMSRouteRedirectChain,
  performCMSRouteRedirect,
}));

vi.mock('@/features/cms/components/useCMSPage', () => ({useCMSPage}));

vi.mock('@/features/cms/components/BlockRenderer', () => ({
  BlockRenderer: () => <div data-testid="blocks" />,
}));

vi.mock('@/routes/NotFoundPage', () => ({
  NotFoundPage: () => <div data-testid="not-found" />,
}));

import {CMSPageComponent} from '@/features/cms/components/CMSPageComponent';

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

  it('executes a valid redirect and keeps a loading state during navigation', async () => {
    performCMSRouteRedirect.mockReturnValue('redirected');
    useCMSPage.mockReturnValue({
      page: null,
      redirectTo: '/new',
      loading: false,
      error: null,
      isLivePreview: false,
    });

    const {container} = renderPage('/old?partner=1#details');

    await waitFor(() => {
      expect(performCMSRouteRedirect).toHaveBeenCalledWith('/new');
    });
    expect(container.querySelector('.cms-page-loading')).toBeInTheDocument();
  });

  it('fails closed to NotFound when a redirect is invalid or loops', async () => {
    performCMSRouteRedirect.mockReturnValue('redirect_loop');
    useCMSPage.mockReturnValue({
      page: null,
      redirectTo: '/old',
      loading: false,
      error: null,
      isLivePreview: false,
    });

    renderPage();

    expect(await screen.findByTestId('not-found')).toBeInTheDocument();
  });

  it('shows a load error for non-404 API failures', () => {
    useCMSPage.mockReturnValue({
      page: null,
      redirectTo: null,
      loading: false,
      error: 'error',
      isLivePreview: false,
    });

    renderPage();

    expect(screen.getByText('Something went wrong loading this page.')).toBeInTheDocument();
    expect(screen.queryByTestId('not-found')).not.toBeInTheDocument();
  });

  it('shows NotFound for a missing CMS route', () => {
    useCMSPage.mockReturnValue({
      page: null,
      redirectTo: null,
      loading: false,
      error: 'not_found',
      isLivePreview: false,
    });

    renderPage();

    expect(screen.getByTestId('not-found')).toBeInTheDocument();
  });

  it('clears the prior redirect chain after a normal page response', async () => {
    useCMSPage.mockReturnValue({
      page: {
        slug: 'new',
        route: '/new',
        title: 'New page',
        page_css_class: '',
        page_css: '',
        meta_description: '',
        blocks: [],
      },
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: false,
    });

    renderPage('/new');

    expect(screen.getByTestId('blocks')).toBeInTheDocument();
    await waitFor(() => expect(clearCMSRouteRedirectChain).toHaveBeenCalled());
  });

  it('never executes redirects in preview mode', async () => {
    useCMSPage.mockReturnValue({
      page: null,
      redirectTo: '/new',
      loading: false,
      error: null,
      isLivePreview: false,
    });

    renderPage('/old?cms_preview=1');

    await Promise.resolve();
    expect(performCMSRouteRedirect).not.toHaveBeenCalled();
  });
});
