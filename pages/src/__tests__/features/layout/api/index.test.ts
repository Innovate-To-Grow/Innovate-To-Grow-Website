import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api: apiMock,
}));

import {
  clearLayoutCache,
  fetchLayoutData,
  LAYOUT_CACHE_VERSION,
  readLayoutCache,
  writeLayoutCache,
  type LayoutData,
} from '@/features/layout/api';

const layoutData: LayoutData = {
  menus: [
    {
      id: 'main',
      name: 'main',
      display_name: 'Main Menu',
      description: null,
      items: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ],
  footer: null,
  homepage_route: '/cms/home',
};

describe('layout API cache helpers', () => {
  beforeEach(() => {
    apiMock.get.mockReset();
    window.sessionStorage.clear();
  });

  it('round-trips valid layout data through sessionStorage', () => {
    writeLayoutCache(layoutData);

    expect(readLayoutCache()).toEqual(layoutData);
  });

  it('returns null for missing, malformed, stale, or invalid cached payloads', () => {
    expect(readLayoutCache()).toBeNull();

    window.sessionStorage.setItem('itg-layout-v2', 'not-json');
    expect(readLayoutCache()).toBeNull();

    window.sessionStorage.setItem('itg-layout-v2', JSON.stringify({v: LAYOUT_CACHE_VERSION - 1, data: layoutData}));
    expect(readLayoutCache()).toBeNull();

    window.sessionStorage.setItem('itg-layout-v2', JSON.stringify({v: LAYOUT_CACHE_VERSION, data: {menus: 'bad'}}));
    expect(readLayoutCache()).toBeNull();
  });

  it('ignores storage write/remove failures', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    const removeItem = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('blocked');
    });

    expect(() => writeLayoutCache(layoutData)).not.toThrow();
    expect(() => clearLayoutCache()).not.toThrow();

    setItem.mockRestore();
    removeItem.mockRestore();
  });

  it('deduplicates concurrent layout fetches and resets after completion', async () => {
    apiMock.get.mockResolvedValueOnce({data: layoutData}).mockResolvedValueOnce({data: {...layoutData, homepage_route: '/next'}});

    const [first, second] = await Promise.all([fetchLayoutData(), fetchLayoutData()]);

    expect(first).toEqual(layoutData);
    expect(second).toEqual(layoutData);
    expect(apiMock.get).toHaveBeenCalledTimes(1);
    expect(apiMock.get).toHaveBeenCalledWith('/layout/');

    await expect(fetchLayoutData()).resolves.toMatchObject({homepage_route: '/next'});
    expect(apiMock.get).toHaveBeenCalledTimes(2);
  });
});
