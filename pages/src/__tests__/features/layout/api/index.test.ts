import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {get: mocks.get},
}));

import {
  LAYOUT_CACHE_VERSION,
  clearLayoutCache,
  fetchLayoutData,
  readLayoutCache,
  writeLayoutCache,
} from '@/features/layout/api';

const KEY = 'itg-layout-v3';

function makeData(overrides: Record<string, unknown> = {}) {
  return {menus: [], footer: null, ...overrides};
}

describe('layout api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe('readLayoutCache', () => {
    it('returns null when there is no cached value', () => {
      expect(readLayoutCache()).toBeNull();
    });

    it('returns null when sessionStorage is unavailable', () => {
      vi.stubGlobal('sessionStorage', undefined);
      expect(readLayoutCache()).toBeNull();
    });

    it('returns null for a version mismatch', () => {
      sessionStorage.setItem(KEY, JSON.stringify({v: LAYOUT_CACHE_VERSION + 1, data: makeData()}));
      expect(readLayoutCache()).toBeNull();
    });

    it('returns null for malformed JSON', () => {
      sessionStorage.setItem(KEY, 'not-json{');
      expect(readLayoutCache()).toBeNull();
    });

    it('returns null for a non-object payload', () => {
      sessionStorage.setItem(KEY, '"a string"');
      expect(readLayoutCache()).toBeNull();
    });

    it('returns null for an invalid data shape', () => {
      sessionStorage.setItem(KEY, JSON.stringify({v: LAYOUT_CACHE_VERSION, data: {nope: true}}));
      expect(readLayoutCache()).toBeNull();
    });

    it('returns the cached data when valid', () => {
      const data = makeData({menus: [{id: 'm1'}]});
      sessionStorage.setItem(KEY, JSON.stringify({v: LAYOUT_CACHE_VERSION, data}));
      expect(readLayoutCache()).toEqual(data);
    });
  });

  describe('writeLayoutCache', () => {
    it('stores a versioned payload', () => {
      const data = makeData({menus: [{id: 'm1'}]});
      writeLayoutCache(data);

      const raw = sessionStorage.getItem(KEY)!;
      expect(JSON.parse(raw)).toEqual({v: LAYOUT_CACHE_VERSION, data: {menus: data.menus, footer: null}});
    });

    it('ignores storage write failures', () => {
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new Error('quota');
      });

      expect(() => writeLayoutCache(makeData())).not.toThrow();
    });

    it('no-ops when sessionStorage is unavailable', () => {
      vi.stubGlobal('sessionStorage', undefined);
      expect(() => writeLayoutCache(makeData())).not.toThrow();
    });
  });

  describe('clearLayoutCache', () => {
    it('removes the cached value', () => {
      sessionStorage.setItem(KEY, 'x');
      clearLayoutCache();
      expect(sessionStorage.getItem(KEY)).toBeNull();
    });

    it('ignores remove failures', () => {
      vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
        throw new Error('boom');
      });

      expect(() => clearLayoutCache()).not.toThrow();
    });

    it('no-ops when sessionStorage is unavailable', () => {
      vi.stubGlobal('sessionStorage', undefined);
      expect(() => clearLayoutCache()).not.toThrow();
    });
  });

  describe('fetchLayoutData', () => {
    it('fetches and normalizes the layout', async () => {
      const data = {menus: [{id: 'm1'}], footer: {id: 'f1'}};
      mocks.get.mockResolvedValue({data: {...data, extra: true}});

      await expect(fetchLayoutData()).resolves.toEqual({menus: data.menus, footer: data.footer});
      expect(mocks.get).toHaveBeenCalledWith('/layout/');
    });

    it('deduplicates concurrent requests', async () => {
      let resolve!: (value: {data: {menus: unknown[]; footer: unknown}}) => void;
      mocks.get.mockReturnValue(new Promise((next) => {
        resolve = next;
      }));

      const first = fetchLayoutData();
      const second = fetchLayoutData();

      expect(mocks.get).toHaveBeenCalledTimes(1);

      resolve({data: {menus: [], footer: null}});
      await expect(Promise.all([first, second])).resolves.toEqual([
        {menus: [], footer: null},
        {menus: [], footer: null},
      ]);
    });

    it('clears in-flight state after settling', async () => {
      mocks.get.mockResolvedValue({data: {menus: [], footer: null}});

      await fetchLayoutData();
      await fetchLayoutData();

      expect(mocks.get).toHaveBeenCalledTimes(2);
    });
  });
});
