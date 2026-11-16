// A whole-list load whose pages are requested together: one page refused under load is asked for again, alone,
// instead of failing the whole catalog.
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({get: vi.fn()}));

vi.mock('@/lib/api', () => ({api: apiMock}));
vi.unmock('@/features/projects/api/archive');

import {fetchAllPastProjectArchive, searchPastProjectArchiveIds} from '@/features/projects/api/archive';

const page = (count: number, results: Array<{id: string}>) => ({data: {count, next: null, previous: null, results}});
const failure = (status?: number, extra: Record<string, unknown> = {}) =>
  Object.assign(new Error(`failed ${status ?? 'network'}`), status === undefined ? {} : {response: {status}}, extra);

/** Page n answers with row `p<n>`; `refusals` maps a page number to the failures it gives first, in order. */
function answerPages(count: number, refusals: Record<number, unknown[]> = {}) {
  apiMock.get.mockImplementation((_url: string, {params}: {params: {page: number}}) => {
    const pending = refusals[params.page];
    if (pending?.length) return Promise.reject(pending.shift());
    return Promise.resolve(page(count, [{id: `p${params.page}`}]));
  });
}

const requestedPages = () => apiMock.get.mock.calls.map(([, config]) => config.params.page);

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('fetchAllPastProjectArchive with a failed page', () => {
  it('asks again, after Retry-After, for a page refused with 429, keeping page order', async () => {
    const refusal = failure(429, {response: {status: 429, headers: {'retry-after': '2'}}});
    answerPages(300, {2: [refusal]});

    const loaded = fetchAllPastProjectArchive();
    await vi.advanceTimersByTimeAsync(1999);
    expect(requestedPages()).toEqual([1, 2, 3]);
    await vi.advanceTimersByTimeAsync(1);

    await expect(loaded).resolves.toEqual([{id: 'p1'}, {id: 'p2'}, {id: 'p3'}]);
    expect(requestedPages()).toEqual([1, 2, 3, 2]);
  });

  it('waits the fallback second when the 429 names no wait', async () => {
    answerPages(200, {2: [failure(429)]});

    const loaded = fetchAllPastProjectArchive();
    await vi.advanceTimersByTimeAsync(999);
    expect(requestedPages()).toEqual([1, 2]);
    await vi.advanceTimersByTimeAsync(1);

    await expect(loaded).resolves.toEqual([{id: 'p1'}, {id: 'p2'}]);
  });

  it.each([
    ['a timeout', failure(undefined, {code: 'ECONNABORTED'})],
    ['a 503', failure(503)],
    ['a 408', failure(408)],
  ])('asks again at once after %s', async (_name, reason) => {
    answerPages(200, {2: [reason]});

    await expect(fetchAllPastProjectArchive()).resolves.toEqual([{id: 'p1'}, {id: 'p2'}]);
    expect(requestedPages()).toEqual([1, 2, 2]);
  });

  it('retries each failed page one at a time', async () => {
    answerPages(400, {2: [failure(502)], 4: [failure(504)]});

    await expect(fetchAllPastProjectArchive()).resolves.toEqual([{id: 'p1'}, {id: 'p2'}, {id: 'p3'}, {id: 'p4'}]);
    expect(requestedPages()).toEqual([1, 2, 3, 4, 2, 4]);
  });

  it('fails the list when the page fails a second time', async () => {
    const second = failure(503);
    answerPages(200, {2: [failure(503), second]});

    await expect(fetchAllPastProjectArchive()).rejects.toBe(second);
  });

  it('fails at once on a 429 that asks for longer than the shared client waits', async () => {
    const refusal = {response: {status: 429, headers: {'retry-after': '60'}}};
    answerPages(200, {2: [refusal]});

    await expect(fetchAllPastProjectArchive()).rejects.toBe(refusal);
    expect(requestedPages()).toEqual([1, 2]);
  });

  it('does not ask again for a page that is not a transient failure', async () => {
    const missing = failure(404);
    answerPages(200, {2: [missing]});

    await expect(fetchAllPastProjectArchive()).rejects.toBe(missing);
    expect(requestedPages()).toEqual([1, 2]);
  });

  it.each([
    ['a canceled request', {code: 'ERR_CANCELED'}],
    ['a non-object rejection', 'offline'],
  ])('does not ask again after %s', async (_name, reason) => {
    answerPages(200, {2: [reason]});

    await expect(fetchAllPastProjectArchive()).rejects.toBe(reason);
    expect(requestedPages()).toEqual([1, 2]);
  });

  it('does not ask again once the load was aborted', async () => {
    const controller = new AbortController();
    const reason = failure(503);
    apiMock.get.mockImplementation((_url: string, {params}: {params: {page: number}}) => {
      if (params.page === 1) return Promise.resolve(page(200, [{id: 'p1'}]));
      controller.abort();
      return Promise.reject(reason);
    });

    await expect(fetchAllPastProjectArchive({}, controller.signal)).rejects.toBe(reason);
    expect(requestedPages()).toEqual([1, 2]);
  });

  it('stops waiting for a 429 when the load is aborted during the wait', async () => {
    const controller = new AbortController();
    answerPages(200, {2: [{response: {status: 429, headers: {'retry-after': '5'}}}]});

    const loaded = fetchAllPastProjectArchive({}, controller.signal).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(100);
    controller.abort();

    expect(await loaded).toMatchObject({code: 'ERR_CANCELED'});
    expect(requestedPages()).toEqual([1, 2]);
  });
});

describe('searchPastProjectArchiveIds with a failed page', () => {
  it('asks again for a failed page of the matches too', async () => {
    answerPages(150, {2: [failure(500)]});

    await expect(searchPastProjectArchiveIds('solar')).resolves.toEqual(new Set(['p1', 'p2']));
  });
});
