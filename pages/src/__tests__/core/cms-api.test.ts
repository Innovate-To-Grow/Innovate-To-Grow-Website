import {beforeEach, describe, expect, it, vi} from 'vitest';

const {getMock} = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {get: getMock},
  default: {get: getMock},
}));

import {
  fetchCMSEmbed,
  fetchCMSEmbedHosts,
  fetchCMSLivePreview,
  fetchCMSHomepage,
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

  it('normalizes empty and whitespace-only input to the root path', () => {
    expect(normalizeCMSRoute('')).toBe('/');
    expect(normalizeCMSRoute('   ')).toBe('/');
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

  it('rejects routes containing C0 or DEL control characters', () => {
    expect(() => normalizeCMSRoute('/about\u001fteams')).toThrow();
    expect(() => normalizeCMSRoute('/about\u007f')).toThrow();
  });

  it('rejects invalid percent encoding in a path segment', () => {
    expect(() => normalizeCMSRoute('/about/%zz')).toThrow(
      'CMS route contains invalid percent encoding.',
    );
  });

  it('rejects unsafe decoded path segments', () => {
    expect(() => normalizeCMSRoute('/about/.')).toThrow();
    expect(() => normalizeCMSRoute('/about/%2F')).toThrow();
    expect(() => normalizeCMSRoute('/about/%5C')).toThrow();
    expect(() => normalizeCMSRoute('/about/%00')).toThrow();
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

describe('fetchCMSHomepage', () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it('deduplicates concurrent homepage requests', async () => {
    let resolve!: (value: {data: {route: string}}) => void;
    getMock.mockReturnValue(new Promise((next) => { resolve = next; }));

    const first = fetchCMSHomepage();
    const second = fetchCMSHomepage();

    expect(getMock).toHaveBeenCalledTimes(1);
    expect(getMock).toHaveBeenCalledWith('/cms/homepage/', expect.objectContaining({signal: expect.any(AbortSignal)}));
    resolve({data: {route: '/'}});
    await expect(Promise.all([first, second])).resolves.toEqual([{route: '/'}, {route: '/'}]);
  });

  it('rejects immediately when the consumer signal is already aborted', async () => {
    getMock.mockResolvedValue({data: {route: '/'}});
    const controller = new AbortController();
    controller.abort();

    await expect(fetchCMSHomepage(controller.signal)).rejects.toThrow('The request was aborted.');
    expect(getMock).toHaveBeenCalledTimes(1);
    // Let the shared homepage request settle so it clears before the next test.
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

  it('guards against double release when the signal aborts before resolution', async () => {
    let resolve!: (value: {data: {route: string}}) => void;
    getMock.mockReturnValue(new Promise((next) => { resolve = next; }));

    const controller = new AbortController();
    const pending = fetchCMSHomepage(controller.signal);
    controller.abort();
    resolve({data: {route: '/'}});

    await expect(pending).resolves.toEqual({route: '/'});
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

describe('fetchCMSEmbedHosts', () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValue({data: {hosts: ['a.example'], revision: '1'}});
  });

  it('requests the embed hosts allowlist', async () => {
    await fetchCMSEmbedHosts();

    expect(getMock).toHaveBeenCalledWith('/cms/embed-hosts/');
  });

  it('returns the parsed response body', async () => {
    await expect(fetchCMSEmbedHosts()).resolves.toEqual({
      hosts: ['a.example'],
      revision: '1',
    });
  });
});

describe('fetchCMSEmbed', () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValue({data: {blocks: []}});
  });

  it('requests an embed by slug', async () => {
    await fetchCMSEmbed('schedule');

    expect(getMock).toHaveBeenCalledWith('/cms/embed/schedule/');
  });
});
