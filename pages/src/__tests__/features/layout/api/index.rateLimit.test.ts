// The layout fetch over the real shared client: a first visit refused with 429 still gets its menu and footer once
// the server's Retry-After has passed, and the menu and footer roots still share the one request.
import {AxiosError, AxiosHeaders, type AxiosAdapter} from 'axios';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {fetchLayoutData} from '@/features/layout/api';
import {api} from '@/lib/api';

const originalAdapter = api.defaults.adapter;
const layout = {menus: [{id: 'm1', items: []}], footer: {columns: []}, extra: 'dropped'};

describe('fetchLayoutData under 429', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0);
  });

  afterEach(() => {
    api.defaults.adapter = originalAdapter;
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('waits out Retry-After, retries once and resolves for every root sharing the request', async () => {
    let calls = 0;
    const adapter: AxiosAdapter = async (config) => {
      calls += 1;
      if (calls === 1) {
        const response = {
          status: 429, statusText: '429', data: {code: 'rate_limited', retry_after: 1},
          headers: new AxiosHeaders({'Retry-After': '1'}), config,
        };
        throw new AxiosError('Request failed with status code 429', 'ERR_BAD_REQUEST', config, {}, response);
      }
      return {status: 200, statusText: 'OK', data: layout, headers: new AxiosHeaders(), config};
    };
    api.defaults.adapter = adapter;

    const menuRoot = fetchLayoutData();
    const footerRoot = fetchLayoutData();
    await vi.advanceTimersByTimeAsync(1000);

    const expected = {menus: layout.menus, footer: layout.footer};
    await expect(Promise.all([menuRoot, footerRoot])).resolves.toEqual([expected, expected]);
    expect(calls).toBe(2);
  });
});
