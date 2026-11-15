import {beforeEach, describe, expect, it, vi} from 'vitest';

const {getMock} = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {get: getMock},
  default: {get: getMock},
}));
// fetchCMSEmbedHosts lives in lib/api/embedHosts.ts, which uses the client module directly.
vi.mock('@/lib/api/api-client', () => ({
  api: {get: getMock},
}));

import {
  fetchCMSPage,
} from '@/features/cms/api';

describe('fetchCMSPage', () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValue({data: {route: '/about'}});
  });

  it('uses encoded local API paths', async () => {
    await fetchCMSPage('/about/team_leads', true);

    expect(getMock).toHaveBeenCalledWith('/cms/pages/about/team_leads/?preview=true', {signal: undefined});
  });

  it('encodes legacy punctuation without changing case or falling back to root', async () => {
    await fetchCMSPage('/Archive.v1/~old+page');

    expect(getMock).toHaveBeenCalledWith('/cms/pages/Archive.v1/~old%2Bpage/', {signal: undefined});
  });

  it('does not pass absolute user input into the API URL', async () => {
    await expect(fetchCMSPage('https://example.com/about')).rejects.toThrow();

    expect(getMock).not.toHaveBeenCalled();
  });

  it('builds the collection URL when the normalized route is the root', async () => {
    await fetchCMSPage('/');

    expect(getMock).toHaveBeenCalledWith('/cms/pages/', {signal: undefined});
  });

  it('does not retry a canceled request', async () => {
    getMock.mockRejectedValue({code: 'ERR_CANCELED'});

    await expect(fetchCMSPage('/about')).rejects.toEqual({code: 'ERR_CANCELED'});
    expect(getMock).toHaveBeenCalledTimes(1);
  });

  it('does not retry a non-retryable HTTP status', async () => {
    getMock.mockRejectedValue({response: {status: 404}});

    await expect(fetchCMSPage('/about')).rejects.toEqual({response: {status: 404}});
    expect(getMock).toHaveBeenCalledTimes(1);
  });

  it('retries a retryable status once and returns the eventual response', async () => {
    getMock
      .mockRejectedValueOnce({response: {status: 503, headers: {'retry-after': '0'}}})
      .mockResolvedValueOnce({data: {route: '/about'}});

    await expect(fetchCMSPage('/about')).resolves.toEqual({route: '/about'});
    expect(getMock).toHaveBeenCalledTimes(2);
  });

  it('applies a jittered backoff when no retry-after header is present', async () => {
    getMock
      .mockRejectedValueOnce({response: {status: 502}})
      .mockResolvedValueOnce({data: {route: '/about'}});

    await expect(fetchCMSPage('/about')).resolves.toEqual({route: '/about'});
    expect(getMock).toHaveBeenCalledTimes(2);
  });

  it('honors an HTTP-date retry-after header', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T00:00:00.000Z'));
    try {
      getMock
        .mockRejectedValueOnce({
          response: {
            status: 503,
            headers: {'retry-after': 'Thu, 01 Jan 2026 00:00:02 GMT'},
          },
        })
        .mockResolvedValueOnce({data: {route: '/about'}});

      const pending = fetchCMSPage('/about');
      await vi.advanceTimersByTimeAsync(2000);

      await expect(pending).resolves.toEqual({route: '/about'});
      expect(getMock).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('falls back to jittered backoff for an unparseable retry-after header', async () => {
    getMock
      .mockRejectedValueOnce({
        response: {status: 503, headers: {'retry-after': 'garbage'}},
      })
      .mockResolvedValueOnce({data: {route: '/about'}});

    await expect(fetchCMSPage('/about')).resolves.toEqual({route: '/about'});
    expect(getMock).toHaveBeenCalledTimes(2);
  });

  it('falls back to jittered backoff for an expired retry-after date', async () => {
    getMock
      .mockRejectedValueOnce({
        response: {
          status: 503,
          headers: {'retry-after': 'Thu, 01 Jan 2020 00:00:00 GMT'},
        },
      })
      .mockResolvedValueOnce({data: {route: '/about'}});

    await expect(fetchCMSPage('/about')).resolves.toEqual({route: '/about'});
    expect(getMock).toHaveBeenCalledTimes(2);
  });

  it('waits out a 429 Retry-After longer than the 5xx cap before its one retry', async () => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0);
    try {
      getMock
        .mockRejectedValueOnce({response: {status: 429, headers: {'retry-after': '5'}}})
        .mockResolvedValueOnce({data: {route: '/about'}});

      const pending = fetchCMSPage('/about');
      await vi.advanceTimersByTimeAsync(4999);
      expect(getMock).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(1);

      await expect(pending).resolves.toEqual({route: '/about'});
      expect(getMock).toHaveBeenCalledTimes(2);
    } finally {
      vi.restoreAllMocks();
      vi.useRealTimers();
    }
  });

  it('fails at once on a 429 whose Retry-After is longer than the shared client waits', async () => {
    const refusal = {response: {status: 429, headers: {'retry-after': '60'}}};
    getMock.mockRejectedValueOnce(refusal);

    await expect(fetchCMSPage('/about')).rejects.toBe(refusal);
    expect(getMock).toHaveBeenCalledTimes(1);
  });

  it('does not retry a 429 the shared client already retried', async () => {
    const refusal = {config: {_i2gRateLimitRetried: true}, response: {status: 429, headers: {'retry-after': '1'}}};
    getMock.mockRejectedValueOnce(refusal);

    await expect(fetchCMSPage('/about')).rejects.toBe(refusal);
    expect(getMock).toHaveBeenCalledTimes(1);
  });

  it('aborts a pending retry when the signal fires during backoff', async () => {
    getMock.mockRejectedValueOnce({
      response: {status: 503, headers: {'retry-after': '10'}},
    });
    const controller = new AbortController();
    const pending = fetchCMSPage('/about', false, controller.signal);
    await Promise.resolve();
    await Promise.resolve();

    controller.abort();

    await expect(pending).rejects.toThrow('The request was aborted.');
    expect(getMock).toHaveBeenCalledTimes(1);
  });
});
