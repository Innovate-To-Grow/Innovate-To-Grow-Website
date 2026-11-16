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
  fetchCMSEmbed,
  fetchCMSEmbedHosts,
  fetchCMSLivePreview,
  fetchCMSHomepage,
  fetchCMSPreview,
} from '@/features/cms/api';

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
