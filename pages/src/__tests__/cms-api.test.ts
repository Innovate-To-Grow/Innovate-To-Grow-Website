import {beforeEach, describe, expect, it, vi} from 'vitest';

const {getMock} = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api: {get: getMock},
  default: {get: getMock},
}));

import {
  fetchCMSLivePreview,
  fetchCMSPage,
  fetchCMSPreview,
  normalizeCMSRoute,
} from '@/features/cms/api';

describe('normalizeCMSRoute', () => {
  it('normalizes local CMS route segments', () => {
    expect(normalizeCMSRoute(' about//team-leads/ ')).toBe('/about/team-leads');
    expect(normalizeCMSRoute('/')).toBe('/');
  });

  it('falls back to root for non-CMS paths and URL-like input', () => {
    expect(normalizeCMSRoute('https://example.com/about')).toBe('/');
    expect(normalizeCMSRoute('//example.com/about')).toBe('/');
    expect(normalizeCMSRoute('/about\\team')).toBe('/');
    expect(normalizeCMSRoute('/about/team!')).toBe('/');
  });
});

describe('fetchCMSPage', () => {
  beforeEach(() => {
    getMock.mockResolvedValue({data: {route: '/about'}});
  });

  it('uses encoded local API paths', async () => {
    await fetchCMSPage('/about/team_leads', true);

    expect(getMock).toHaveBeenCalledWith('/cms/pages/about/team_leads/?preview=true');
  });

  it('does not pass absolute user input into the API URL', async () => {
    await fetchCMSPage('https://example.com/about');

    expect(getMock).toHaveBeenCalledWith('/cms/pages/');
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
