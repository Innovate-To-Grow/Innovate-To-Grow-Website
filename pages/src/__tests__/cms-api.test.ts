import {beforeEach, describe, expect, it, vi} from 'vitest';

const {getMock} = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock('../shared/api/client', () => ({
  api: {get: getMock},
  default: {get: getMock},
}));

import {fetchCMSPage, normalizeCMSRoute} from '../features/cms/api';

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
