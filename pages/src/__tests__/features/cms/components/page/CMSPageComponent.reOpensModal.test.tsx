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

  it('re-opens the modal when the badge is clicked', () => {
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
