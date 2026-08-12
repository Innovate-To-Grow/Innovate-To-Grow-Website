import {beforeEach, describe, expect, it, vi} from 'vitest';

const {getMock} = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {get: getMock},
  default: {get: getMock},
}));

import {
  fetchCMSLivePreview,
  fetchCMSPage,
  fetchCMSPreview,
  isCMSPageRedirectResponse,
  normalizeCMSRoute,
} from '@/features/cms/api';

describe('normalizeCMSRoute', () => {
  it('normalizes local CMS route segments', () => {
    expect(normalizeCMSRoute(' about//team-leads/ ')).toBe('/about/team-leads');
    expect(normalizeCMSRoute('/')).toBe('/');
  });

  it('preserves case and safe punctuation used by legacy paths', () => {
    expect(normalizeCMSRoute('/FAQs')).toBe('/FAQs');
    expect(normalizeCMSRoute('/Archive.v1/~old+page')).toBe('/Archive.v1/~old+page');
    expect(normalizeCMSRoute('/Archive%2Ev1')).toBe('/Archive.v1');
  });

  it('rejects unsafe input instead of silently requesting the root page', () => {
    expect(() => normalizeCMSRoute('https://example.com/about')).toThrow();
    expect(() => normalizeCMSRoute('//example.com/about')).toThrow();
    expect(() => normalizeCMSRoute('/about\\team')).toThrow();
    expect(() => normalizeCMSRoute('/about?preview=true')).toThrow();
    expect(() => normalizeCMSRoute('/about/%2e%2e/admin')).toThrow();
  });
});

describe('isCMSPageRedirectResponse', () => {
  it('only accepts permanent redirect payloads', () => {
    expect(isCMSPageRedirectResponse({redirect_to: '/faqs', permanent: true})).toBe(true);
    expect(isCMSPageRedirectResponse({
      slug: 'faqs',
      route: '/faqs',
      title: 'FAQs',
      page_css_class: '',
      page_css: '',
      meta_description: '',
      blocks: [],
    })).toBe(false);
  });
});

describe('fetchCMSPage', () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValue({data: {route: '/about'}});
  });

  it('uses encoded local API paths', async () => {
    await fetchCMSPage('/about/team_leads', true);

    expect(getMock).toHaveBeenCalledWith('/cms/pages/about/team_leads/?preview=true');
  });

  it('encodes legacy punctuation without changing case or falling back to root', async () => {
    await fetchCMSPage('/Archive.v1/~old+page');

    expect(getMock).toHaveBeenCalledWith('/cms/pages/Archive.v1/~old%2Bpage/');
  });

  it('does not pass absolute user input into the API URL', async () => {
    await expect(fetchCMSPage('https://example.com/about')).rejects.toThrow();

    expect(getMock).not.toHaveBeenCalled();
  });
});

describe('fetchCMSPreview', () => {
  beforeEach(() => {
    getMock.mockResolvedValue({data: {route: '/about'}});
  });

  it('encodes the preview token in the API URL', async () => {
    await fetchCMSPreview('opaque-token');

    expect(getMock).toHaveBeenCalledWith('/cms/preview/opaque-token/');
  });

  it('does not let a token escape its path segment', async () => {
    await fetchCMSPreview('../live-preview/evil');

    expect(getMock).toHaveBeenCalledWith('/cms/preview/..%2Flive-preview%2Fevil/');
  });
});

describe('fetchCMSLivePreview', () => {
  beforeEach(() => {
    getMock.mockResolvedValue({data: {route: '/about'}});
  });

  it('encodes the page id in the API URL', async () => {
    await fetchCMSLivePreview('11111111-1111-1111-1111-111111111111');

    expect(getMock).toHaveBeenCalledWith(
      '/cms/live-preview/11111111-1111-1111-1111-111111111111/',
    );
  });

  it('does not let a page id escape its path segment', async () => {
    await fetchCMSLivePreview('../preview/evil');

    expect(getMock).toHaveBeenCalledWith('/cms/live-preview/..%2Fpreview%2Fevil/');
  });
});
