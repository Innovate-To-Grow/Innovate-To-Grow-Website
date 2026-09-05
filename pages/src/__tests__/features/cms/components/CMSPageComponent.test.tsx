import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
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
    const retry = vi.fn();
    useCMSPage.mockReturnValue({
      page: null,
      redirectTo: null,
      loading: false,
      error: 'error',
      isLivePreview: false,
      retry,
    });

    renderPage();

    expect(screen.getByText('Something went wrong loading this page.')).toBeInTheDocument();
    expect(screen.queryByTestId('not-found')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Try again'}));
    expect(retry).toHaveBeenCalledOnce();
  });

  it('renders an accessible loading shell with reserved content space', () => {
    useCMSPage.mockReturnValue({
      page: null,
      redirectTo: null,
      loading: true,
      error: null,
      isLivePreview: false,
      retry: vi.fn(),
    });

    const {container} = renderPage();

    expect(screen.getByRole('status', {name: 'Loading page content'})).toBeInTheDocument();
    expect(container.querySelector('.cms-page-shell')).toHaveAttribute('aria-busy', 'true');
    expect(container.querySelectorAll('.cms-page-skeleton')).toHaveLength(3);
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

  it('shows NotFound when no page, error, or redirect is present', () => {
    useCMSPage.mockReturnValue({
      page: null,
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: false,
    });

    renderPage('/missing');

    expect(screen.getByTestId('not-found')).toBeInTheDocument();
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
    expect(screen.queryByRole('button', {name: 'Try again'})).toBeNull();
  });

  it('injects per-page CSS and clears it on unmount', () => {
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

    const {unmount, container} = renderPage('/styled');

    expect(container.querySelector('.custom-page')).not.toBeNull();
    const style = document.getElementById('itg-page-css');
    expect(style).not.toBeNull();
    expect(style?.textContent).toBe('body { color: red; }');

    unmount();
    expect(document.getElementById('itg-page-css')?.textContent).toBe('');
  });

  it('reuses the existing style element for subsequent pages', () => {
    const base = {
      slug: 'styled',
      route: '/styled',
      title: 'Styled page',
      page_css_class: 'custom-page',
      meta_description: '',
      blocks: [],
    };
    useCMSPage.mockReturnValue({
      page: {...base, page_css: 'a{}'},
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: false,
    });

    const first = renderPage('/styled');
    first.unmount();

    useCMSPage.mockReturnValue({
      page: {...base, page_css: 'b{}'},
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: false,
    });
    renderPage('/styled');

    const style = document.getElementById('itg-page-css');
    expect(style?.textContent).toBe('b{}');
    expect(document.querySelectorAll('#itg-page-css')).toHaveLength(1);
  });

  it('shows the live preview modal with expiry and a title suffix', () => {
    useCMSPage.mockReturnValue({
      page: {
        slug: 'live',
        route: '/live',
        title: 'Draft page',
        page_css_class: '',
        page_css: '',
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
        page_css: '',
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
  });

  it('dismisses the modal when the overlay backdrop is clicked', () => {
    useCMSPage.mockReturnValue({
      page: {
        slug: 'live',
        route: '/live',
        title: 'Draft page',
        page_css_class: '',
        page_css: '',
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

  it('re-opens the modal when the badge is clicked', () => {
    useCMSPage.mockReturnValue({
      page: {
        slug: 'live',
        route: '/live',
        title: 'Draft page',
        page_css_class: '',
        page_css: '',
        meta_description: '',
        blocks: [],
      },
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: true,
    });

    renderPage('/live');

    fireEvent.click(screen.getByRole('button', {name: 'OK'}));
    fireEvent.click(screen.getByText('CMS Preview'));

    expect(
      screen.getByText(
        'Previewing This Page With Content Management System with Admin Permission',
      ),
    ).toBeInTheDocument();
  });
});
