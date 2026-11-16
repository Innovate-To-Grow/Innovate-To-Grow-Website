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

const blockHeading = vi.hoisted(() => ({text: null as string | null}));

vi.mock('@/features/cms/components/BlockRenderer', () => ({
  BlockRenderer: () => (
    <div data-testid="blocks">{blockHeading.text ? <h1>{blockHeading.text}</h1> : null}</div>
  ),
}));

vi.mock('@/components/NotFoundPage', () => ({
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

describe('CMSPageComponent page title', () => {
  const page = {
    id: 'page-1',
    title: 'Fall 2020 Event',
    route: '/2020-fall-event',
    blocks: [],
    page_css_class: '',
  };

  beforeEach(() => {
    useCMSPage.mockReset();
    blockHeading.text = null;
  });

  afterEach(() => {
    cleanup();
  });

  it('adds a visually hidden h1 from the CMS title when no block renders one', async () => {
    useCMSPage.mockReturnValue({page, redirectTo: null, loading: false, error: null, isLivePreview: false});

    renderPage('/2020-fall-event');

    const heading = await screen.findByRole('heading', {level: 1, name: 'Fall 2020 Event'});
    expect(heading).toHaveClass('sr-only');
    expect(document.title).toBe('Fall 2020 Event | Innovate to Grow');
  });

  it("names og:title and the meta description after the page, replacing the previous page's", () => {
    document.head.innerHTML = '<meta property="og:title" content="Current Projects">';
    useCMSPage.mockReturnValue({
      page: {...page, meta_description: 'Teams presented their projects at the Fall 2020 showcase.'},
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: false,
    });

    renderPage('/2020-fall-event');

    const meta = (selector: string) => document.head.querySelector<HTMLMetaElement>(selector)?.content;
    expect(meta('meta[property="og:title"]')).toBe('Fall 2020 Event');
    expect(meta('meta[name="description"]')).toBe('Teams presented their projects at the Fall 2020 showcase.');
    expect(meta('meta[property="og:description"]')).toBe('Teams presented their projects at the Fall 2020 showcase.');
  });

  it('adds no extra h1 when a block already renders one', async () => {
    blockHeading.text = 'About Us';
    useCMSPage.mockReturnValue({page, redirectTo: null, loading: false, error: null, isLivePreview: false});

    renderPage('/about');

    await waitFor(() => expect(screen.getAllByRole('heading', {level: 1})).toHaveLength(1));
    expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('About Us');
  });
});
